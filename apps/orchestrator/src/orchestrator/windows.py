from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from typing import Tuple


def is_windows() -> bool:
    """Check if the current platform is Windows."""
    return os.name == "nt"


async def run_command(cmd: list[str]) -> Tuple[bool, str]:
    """Execute a system command. On non-Windows platforms, simulates execution."""
    cmd_str = " ".join(cmd)
    if is_windows():
        def _run() -> Tuple[bool, str]:
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return True, res.stdout
            except subprocess.CalledProcessError as e:
                return False, f"Command failed: {e.stderr}\nOutput: {e.stdout}"
        return await asyncio.to_thread(_run)
    else:
        print(f"[SIMULATED WINDOWS COMMAND]: {cmd_str}", file=sys.stderr)
        return True, f"Simulated execution on non-Windows OS of: {cmd_str}"


async def create_user(username: str, password: str) -> None:
    """Create a Windows local user with the given password.

    Raises RuntimeError if the command fails and the user does not already exist.
    """
    success, msg = await run_command(["net", "user", username, password, "/add", "/y"])
    if not success and "exists" not in msg.lower():
        raise RuntimeError(f"Failed to create user '{username}': {msg}")


async def delete_user(username: str) -> None:
    """Delete a Windows local user account.

    Raises RuntimeError if the command fails and the user was not already absent.
    """
    success, msg = await run_command(["net", "user", username, "/delete"])
    if not success and "not found" not in msg.lower():
        raise RuntimeError(f"Failed to delete user '{username}': {msg}")


async def add_to_rdp_group(username: str) -> None:
    """Add a user to the Remote Desktop Users group.

    Handles locale-specific group name variants (English and Spanish).
    """
    success, msg = await run_command(
        ["net", "localgroup", "Remote Desktop Users", username, "/add"]
    )
    if not success and "already" not in msg.lower():
        success, msg = await run_command(
            ["net", "localgroup", "Usuarios de escritorio remoto", username, "/add"]
        )
        if not success and "already" not in msg.lower():
            print(
                f"[WARNING]: Could not add '{username}' to RDP group: {msg}",
                file=sys.stderr,
            )


async def load_registry_hive(username: str) -> str:
    """Load a user's NTUSER.DAT into a temporary registry hive.

    Returns the hive name (e.g. 'TempHive_savisor-julio').
    Raises RuntimeError on failure.
    """
    ntuser_path = f"C:\\Users\\{username}\\NTUSER.DAT"
    hive_name = f"TempHive_{username}"
    success, msg = await run_command(["reg", "load", f"HKLM\\{hive_name}", ntuser_path])
    if not success:
        raise RuntimeError(
            f"Failed to load NTUSER.DAT hive for '{username}' "
            f"(user may need to login once first): {msg}"
        )
    return hive_name


async def set_shell_override(hive_name: str, script_path: str) -> None:
    """Write a custom Winlogon Shell key in a loaded registry hive.

    Raises RuntimeError on failure.
    """
    success, msg = await run_command([
        "reg", "add",
        f"HKLM\\{hive_name}\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon",
        "/v", "Shell",
        "/t", "REG_SZ",
        "/d", script_path,
        "/f",
    ])
    if not success:
        raise RuntimeError(f"Failed to set shell override in '{hive_name}': {msg}")


async def unload_registry_hive(hive_name: str) -> None:
    """Unload a previously loaded registry hive.

    Raises RuntimeError on failure.
    """
    success, msg = await run_command(["reg", "unload", f"HKLM\\{hive_name}"])
    if not success:
        raise RuntimeError(f"Failed to unload registry hive '{hive_name}': {msg}")


async def logoff_user(username: str) -> None:
    """Force logoff any active RDP session for the given user.

    Uses `query session` to find the session ID and `logoff` to terminate it.
    Silently succeeds if the user has no active session.
    """
    if not is_windows():
        print(f"[SIMULATED]: logoff user '{username}'", file=sys.stderr)
        return

    def _logoff() -> None:
        try:
            result = subprocess.run(
                ["query", "session", username],
                capture_output=True, text=True,
            )
            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    session_id = parts[2] if parts[2].isdigit() else parts[1]
                    if session_id.isdigit():
                        subprocess.run(
                            ["logoff", session_id], capture_output=True, text=True
                        )
        except Exception:
            pass

    await asyncio.to_thread(_logoff)
