from __future__ import annotations

import secrets
import string
import sys
from pathlib import Path

from orchestrator.config import Settings
from orchestrator.store import TraderMapping, TraderStore
from orchestrator.windows import (
    add_to_rdp_group,
    create_user,
    delete_user,
    load_registry_hive,
    logoff_user,
    set_shell_override,
    unload_registry_hive,
)


class ProvisioningError(Exception):
    """Raised when any step of the provisioning pipeline fails."""


class Provisioner:
    """Handles the full lifecycle of trader provisioning and deprovisioning.

    Provisioning pipeline:
        1. Allocate a loopback port
        2. Generate a secure password
        3. Create Windows user + grant RDP access
        4. Write a per-user startup script (with port baked in)
        5. Configure the registry custom shell override
        6. Generate an RDP connection profile
        7. Persist the mapping to the store

    On failure at any step, a best-effort rollback is performed.
    """

    def __init__(self, settings: Settings, store: TraderStore) -> None:
        self.settings = settings
        self.store = store
        self.scripts_dir = (
            settings.scripts_dir
            if settings.scripts_dir.is_absolute()
            else settings.base_dir / settings.scripts_dir
        )
        self.rdp_profiles_dir = (
            settings.rdp_profiles_dir
            if settings.rdp_profiles_dir.is_absolute()
            else settings.base_dir / settings.rdp_profiles_dir
        )

    async def provision(self, organization: str, trader_name: str) -> TraderMapping:
        """Run the full provisioning pipeline for a new trader.

        Returns the TraderMapping if the trader already exists (idempotent).
        Raises ProvisioningError on failure.
        """
        username = f"{organization.lower()}-{trader_name.lower()}"
        instance_dir = self.settings.base_dir / "instances" / username

        # Idempotent: return existing mapping if already provisioned
        existing = await self.store.get_trader(username)
        if existing is not None:
            return existing

        port = await self.store.get_next_port(
            self.settings.port_range_start, self.settings.port_range_end
        )
        password = self._generate_password()

        try:
            # Step 1: Create Windows user
            await create_user(username, password)
            await add_to_rdp_group(username)

            # Step 2: Setup isolated directory and copy terminal + config
            await self._setup_instance_directory(username, instance_dir)

            # Step 3: Write per-user startup script
            script_path = self._write_startup_script(username, port, instance_dir)

            # Step 4: Configure registry custom shell
            await self._configure_shell(username, str(script_path))

            # Step 5: Generate RDP profile
            rdp_path = self._write_rdp_profile(username)

            # Step 6: Persist mapping
            mapping = TraderMapping(
                port=port,
                password=password,
                rdp_profile=str(rdp_path),
                organization=organization,
                trader_name=trader_name,
            )
            await self.store.upsert_trader(username, mapping)

            return mapping

        except Exception as e:
            print(
                f"[ERROR] Provisioning failed for '{username}', rolling back: {e}",
                file=sys.stderr,
            )
            await self._rollback(username)
            raise ProvisioningError(
                f"Failed to provision trader '{username}': {e}"
            ) from e

    async def deprovision(self, username: str) -> bool:
        """Fully deprovision a trader: logoff session, delete user, remove mapping.

        Returns True if the trader was found and removed.
        """
        existing = await self.store.get_trader(username)
        if existing is None:
            return False

        # Force logoff any active RDP session
        try:
            await logoff_user(username)
        except Exception as e:
            print(f"[WARNING] logoff_user failed for '{username}': {e}", file=sys.stderr)

        # Delete Windows user account
        try:
            await delete_user(username)
        except Exception as e:
            print(f"[WARNING] delete_user failed for '{username}': {e}", file=sys.stderr)

        # Remove startup script if it exists
        script_file = (
            self.scripts_dir / f"start-session-{username}.bat"
        )
        if script_file.exists():
            try:
                script_file.unlink()
            except OSError:
                pass

        # Remove RDP profile if it exists
        rdp_file = self.rdp_profiles_dir / f"{username}.rdp"
        if rdp_file.exists():
            try:
                rdp_file.unlink()
            except OSError:
                pass

        # Remove user isolated directory and files
        instance_dir = self.settings.base_dir / "instances" / username
        if instance_dir.exists():
            try:
                def _rmtree():
                    import shutil
                    import os
                    # Reset read-only attributes that MT5 may set on files
                    for root, dirs, files in os.walk(str(instance_dir)):
                        for file in files:
                            p = os.path.join(root, file)
                            try:
                                os.chmod(p, 0o777)
                            except OSError:
                                pass
                    shutil.rmtree(str(instance_dir), ignore_errors=True)
                await asyncio.to_thread(_rmtree)
            except Exception as e:
                print(f"[WARNING] Failed to remove instance directory '{instance_dir}': {e}", file=sys.stderr)

        # Remove from mapping store
        return await self.store.remove_trader(username)

    async def _configure_shell(self, username: str, script_path: str) -> None:
        """Load the user's registry hive and inject the custom Winlogon shell."""
        hive_name = None
        try:
            hive_name = await load_registry_hive(username)
            await set_shell_override(hive_name, script_path)
        except RuntimeError as e:
            print(
                f"[WARNING] Registry shell override failed for '{username}': {e}",
                file=sys.stderr,
            )
        finally:
            if hive_name is not None:
                try:
                    await unload_registry_hive(hive_name)
                except RuntimeError:
                    pass

    def _write_startup_script(self, username: str, port: int, instance_dir: Path) -> Path:
        """Generate a per-user startup batch script with the port baked in."""
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        script_path = self.scripts_dir / f"start-session-{username}.bat"
        base_dir = self.settings.base_dir
        terminal_dir = instance_dir / "terminal"

        # Ensure the centralized session-monitor.ps1 is copied to scripts_dir
        template_src = Path(__file__).parent / "templates" / "session-monitor.ps1"
        target_monitor_path = self.scripts_dir / "session-monitor.ps1"
        if template_src.exists():
            import shutil
            shutil.copy2(template_src, target_monitor_path)

        content = (
            f"@echo off\r\n"
            f"title MetaTrader 5 Session - {username}\r\n"
            f"powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"{target_monitor_path.absolute()}\" "
            f"-Username \"{username}\" -Port {port} -BaseDir \"{base_dir}\" -TerminalDir \"{terminal_dir}\"\r\n"
        )
        script_path.write_text(content)
        return script_path.absolute()

    def _write_rdp_profile(self, username: str) -> Path:
        """Generate an RDP connection profile for the trader."""
        self.rdp_profiles_dir.mkdir(parents=True, exist_ok=True)
        rdp_path = self.rdp_profiles_dir / f"{username}.rdp"
        script_path = self.scripts_dir / f"start-session-{username}.bat"

        content = (
            f"# Savisor Remote Desktop Profile\r\n"
            f"auto connect:i:1\r\n"
            f"full address:s:{self.settings.rdp_server_address}\r\n"
            f"username:s:{username}\r\n"
            f"screen mode id:i:2\r\n"
            f"use multimon:i:0\r\n"
            f"session bpp:i:32\r\n"
            f"alternate shell:s:{script_path.absolute()}\r\n"
            f"shell working directory:s:{self.scripts_dir.absolute()}\r\n"
            f"connect to console:i:0\r\n"
            f"disable wallpaper:i:1\r\n"
            f"disable full window drag:i:1\r\n"
            f"disable menu anims:i:1\r\n"
            f"disable themes:i:1\r\n"
            f"bitmapcachepersistenable:i:1\r\n"
        )
        rdp_path.write_text(content)
        return rdp_path.absolute()

    async def _rollback(self, username: str) -> None:
        """Best-effort cleanup after a failed provisioning attempt."""
        try:
            await delete_user(username)
        except Exception:
            pass

        script_file = self.scripts_dir / f"start-session-{username}.bat"
        if script_file.exists():
            try:
                script_file.unlink()
            except OSError:
                pass

        rdp_file = self.rdp_profiles_dir / f"{username}.rdp"
        if rdp_file.exists():
            try:
                rdp_file.unlink()
            except OSError:
                pass

        # Remove user isolated directory
        instance_dir = self.settings.base_dir / "instances" / username
        if instance_dir.exists():
            try:
                def _rmtree():
                    import shutil
                    import os
                    for root, dirs, files in os.walk(str(instance_dir)):
                        for file in files:
                            p = os.path.join(root, file)
                            try:
                                os.chmod(p, 0o777)
                            except OSError:
                                pass
                    shutil.rmtree(str(instance_dir), ignore_errors=True)
                await asyncio.to_thread(_rmtree)
            except Exception:
                pass

        await self.store.remove_trader(username)

    async def _setup_instance_directory(self, username: str, instance_dir: Path) -> None:
        """Create the user's isolated directory and copy terminal templates + config."""
        import shutil
        import asyncio
        from orchestrator.windows import run_command

        # Create instance dir if not exists
        instance_dir.mkdir(parents=True, exist_ok=True)

        # Copy the master terminal to the user's instance folder
        master_terminal = self.settings.master_terminal_dir
        user_terminal = instance_dir / "terminal"

        if master_terminal.exists() and not user_terminal.exists():
            # Copy terminal folder
            def _copy():
                shutil.copytree(master_terminal, user_terminal, dirs_exist_ok=True)
            await asyncio.to_thread(_copy)

        # Ensure a blank portable.tst is present in the user's terminal directory
        if user_terminal.exists():
            portable_tst = user_terminal / "portable.tst"
            if not portable_tst.exists():
                portable_tst.touch()

            # Inject the common.ini maximized configuration file
            config_dir = user_terminal / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            
            template_ini = Path(__file__).parent / "templates" / "common.ini"
            target_ini = config_dir / "common.ini"
            if template_ini.exists():
                shutil.copy2(template_ini, target_ini)

        # Apply strict NTFS ACL permissions via icacls.exe to prevent cross-contamination
        # 1. Disable inheritance and copy current permissions
        await run_command(["icacls", str(instance_dir), "/inheritance:d"])
        # 2. Remove standard Users and Everyone group access
        await run_command(["icacls", str(instance_dir), "/remove", "Users"])
        await run_command(["icacls", str(instance_dir), "/remove", "Everyone"])
        # 3. Grant Full Control to the specific trader and Administrators
        await run_command(["icacls", str(instance_dir), "/grant:r", f"{username}:(OI)(CI)F"])
        await run_command(["icacls", str(instance_dir), "/grant:r", f"Administrators:(OI)(CI)F"])

    @staticmethod
    def _generate_password(length: int = 16) -> str:
        """Generate a secure password meeting Windows Server complexity requirements."""
        upper = string.ascii_uppercase
        lower = string.ascii_lowercase
        digits = string.digits
        special = "!@#$%"

        all_chars = upper + lower + digits + special
        password = [
            secrets.choice(upper),
            secrets.choice(lower),
            secrets.choice(digits),
            secrets.choice(special),
        ]
        password += [secrets.choice(all_chars) for _ in range(length - 4)]
        secrets.SystemRandom().shuffle(password)
        return "".join(password)
