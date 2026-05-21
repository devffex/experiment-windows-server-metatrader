param (
    [string]$CloudflareToken = ""
)

# 1. Enforce Administrator elevation
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "ERROR: This script must be run as an Administrator. Please run PowerShell as Administrator."
    exit 1
}

Write-Host "========================================================="
Write-Host "Savisor MetaTrader Server Bootstrapper & Provisioner"
Write-Host "========================================================="

# 2. Establish directories
$BaseDir = "C:\savisor"
$TerminalDir = "$BaseDir\terminal"
$ScriptsDir = "$BaseDir\scripts"
$LogsDir = "$BaseDir\logs"
$TempDir = "$BaseDir\temp"

Write-Host "Creating server directory layouts..."
foreach ($dir in @($BaseDir, $TerminalDir, $ScriptsDir, $LogsDir, $TempDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
}

# Ensure TLS 1.2
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# 3. Check / Download Python
$PythonExe = Get-Command "python" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $PythonExe) {
    Write-Host "Python not found. Downloading Python 3.10.11 silent installer..."
    $PythonUrl = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
    $InstallerPath = "$TempDir\python-installer.exe"
    
    try {
        Invoke-WebRequest -Uri $PythonUrl -OutFile $InstallerPath -UseBasicParsing
        Write-Host "Installing Python silently (adding to PATH)..."
        Start-Process -FilePath $InstallerPath -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1" -Wait
        Start-Sleep -Seconds 5
        $PythonExe = "C:\Program Files\Python310\python.exe"
        if (-not (Test-Path $PythonExe)) {
            $PythonExe = Get-Command "python" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
        }
        Write-Host "Python successfully installed: $PythonExe"
    } catch {
        Write-Error "Failed to install Python automatically: $_"
        exit 1
    }
} else {
    Write-Host "Python is already installed: $PythonExe"
}

# 4. Check / Download Git
$GitExe = Get-Command "git" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $GitExe) {
    Write-Host "Git not found. Installing Git via Winget..."
    try {
        Start-Process -FilePath "winget" -ArgumentList "install --id Git.Git -e --silent --accept-source-agreements --accept-package-agreements" -Wait
        $GitExe = Get-Command "git" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
        Write-Host "Git successfully installed."
    } catch {
        Write-Warning "Winget failed. Downloading Git installer..."
        $GitUrl = "https://github.com/git-for-windows/git/releases/download/v2.40.1.windows.1/Git-2.40.1-64-bit.exe"
        $GitInstaller = "$TempDir\git-installer.exe"
        Invoke-WebRequest -Uri $GitUrl -OutFile $GitInstaller -UseBasicParsing
        Start-Process -FilePath $GitInstaller -ArgumentList "/VERYSILENT /NORESTART" -Wait
        Write-Host "Git successfully installed."
    }
} else {
    Write-Host "Git is already installed."
}

# 5. Build system-wide Virtual Environment
$VenvDir = "$BaseDir\.venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating Python Virtual Environment at $VenvDir..."
    & $PythonExe -m venv $VenvDir
}
$VenvPython = "$VenvDir\Scripts\python.exe"

# Upgrade pip and install uv package manager
Write-Host "Upgrading pip and installing uv package manager..."
& $VenvPython -m pip install --upgrade pip | Out-Null
& $VenvPython -m pip install uv | Out-Null
$UvExe = "$VenvDir\Scripts\uv.exe"

# 6. Pull the code repository and install dependencies
$WorkspacePath = "$BaseDir\experiment-windows-server-metatrader"
if (-not (Test-Path $WorkspacePath)) {
    Write-Host "Cloning Savisor repository into $WorkspacePath..."
    # If this is run locally inside the existing repository, copy it
    if (Test-Path "$PSScriptRoot\.git") {
        Write-Host "Local codebase found. Copying codebase..."
        Copy-Item -Path $PSScriptRoot -Destination $WorkspacePath -Recurse -Force
    } else {
        # Fallback to cloning from active repository remote
        & git clone https://github.com/Savisor/experiment-windows-server-metatrader.git $WorkspacePath
    }
}

# Synchronize python packages using uv
Write-Host "Syncing and installing dependencies using uv..."
if (Test-Path "$WorkspacePath\pyproject.toml") {
    & $UvExe pip install -r "$WorkspacePath\pyproject.toml"
    # Also install editable projects in workspace
    & $UvExe pip install -e "$WorkspacePath\packages\shared-schemas"
    & $UvExe pip install -e "$WorkspacePath\apps\session-wrapper"
    & $UvExe pip install -e "$WorkspacePath\apps\orchestrator"
} else {
    & $VenvPython -m pip install fastapi uvicorn pydantic psutil pywin32 pandas numpy httpx python-multipart pydantic-settings
}

# 7. Pull and Compile Portable MetaTrader 5 Terminal
$Mt5Installer = "$TempDir\mt5setup.exe"
if (-not (Test-Path "$TerminalDir\terminal64.exe")) {
    Write-Host "Downloading MetaTrader 5 official installer..."
    $Mt5Url = "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
    try {
        Invoke-WebRequest -Uri $Mt5Url -OutFile $Mt5Installer -UseBasicParsing
        Write-Host "Running MT5 Setup silently..."
        $SilentInstallDir = "$TempDir\mt5-temp"
        
        # Run silent installer
        $Process = Start-Process -FilePath $Mt5Installer -ArgumentList "/S /D=$SilentInstallDir" -Wait -PassThru
        Start-Sleep -Seconds 10
        
        # Verify and copy files to golden master
        $DefaultProgramPath = "C:\Program Files\MetaTrader 5"
        $SourcePath = ""
        if (Test-Path "$SilentInstallDir\terminal64.exe") {
            $SourcePath = $SilentInstallDir
        } elseif (Test-Path "$DefaultProgramPath\terminal64.exe") {
            $SourcePath = $DefaultProgramPath
        } else {
            # Try searching in LocalAppData
            $LocalAppPath = "$env:LOCALAPPDATA\MetaTrader 5"
            if (Test-Path "$LocalAppPath\terminal64.exe") {
                $SourcePath = $LocalAppPath
            }
        }

        if ($SourcePath) {
            Write-Host "Extracting MetaTrader 5 terminal from $SourcePath to golden master: $TerminalDir"
            Copy-Item -Path "$SourcePath\*" -Destination $TerminalDir -Recurse -Force
            # Force portable mode by creating portable.tst
            New-Item -ItemType File -Path "$TerminalDir\portable.tst" -Force | Out-Null
            Write-Host "Golden master terminal compiled."
        } else {
            Write-Warning "Could not locate installed terminal64.exe automatically."
            Write-Host "Please place a clean copy of terminal64.exe under: $TerminalDir"
        }
    } catch {
        Write-Error "Failed to install MT5 silently: $_"
    }
} else {
    Write-Host "Golden master MetaTrader 5 terminal already compiled."
}

# Ensure blank portable.tst is in the master terminal folder
if (-not (Test-Path "$TerminalDir\portable.tst")) {
    New-Item -ItemType File -Path "$TerminalDir\portable.tst" -Force | Out-Null
}

# 8. Setup Cloudflare Tunnel
$CloudflaredExe = "$BaseDir\cloudflared.exe"
if (-not (Test-Path $CloudflaredExe)) {
    Write-Host "Downloading Cloudflare Tunnel CLI (cloudflared)..."
    $CfUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    try {
        Invoke-WebRequest -Uri $CfUrl -OutFile $CloudflaredExe -UseBasicParsing
        Write-Host "Cloudflare tunnel client successfully saved to: $CloudflaredExe"
    } catch {
        Write-Error "Failed to download cloudflared: $_"
    }
}

if (![string]::IsNullOrEmpty($CloudflareToken)) {
    Write-Host "Installing Cloudflare Tunnel as a persistent Windows Service..."
    $existingCf = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
    if ($existingCf) {
        Write-Host "Removing existing cloudflared service..."
        & $CloudflaredExe service uninstall | Out-Null
        Start-Sleep -Seconds 1
    }
    
    # Install as service
    & $CloudflaredExe service install $CloudflareToken
    Start-Sleep -Seconds 1
    $cfStatus = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
    if ($cfStatus -and $cfStatus.Status -eq "Running") {
        Write-Host "SUCCESS: Cloudflare Tunnel Service is running."
    } else {
        if ($cfStatus) {
            Start-Service -Name "cloudflared" -ErrorAction SilentlyContinue
            $cfStatus = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
            Write-Host "Cloudflare service status is: $($cfStatus.Status)"
        }
    }
} else {
    Write-Host "========================================================="
    Write-Host "INFO: No Cloudflare Token provided."
    Write-Host "To expose the orchestrator safely via Cloudflare Tunnel, run:"
    Write-Host "C:\savisor\cloudflared.exe service install <YOUR_TUNNEL_TOKEN>"
    Write-Host "========================================================="
}

# 9. Register Orchestrator System Service
$ServiceInstaller = "$WorkspacePath\apps\orchestrator\install-orchestrator-service.ps1"
if (Test-Path $ServiceInstaller) {
    Write-Host "Triggering Orchestrator Service installation..."
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ServiceInstaller
}

# 10. Clean up Temp directory
Write-Host "Cleaning up installation temporary files..."
if (Test-Path $TempDir) {
    Remove-Item -Path "$TempDir\*" -Recurse -Force -ErrorAction SilentlyContinue | Out-Null
}

Write-Host "========================================================="
Write-Host "SUCCESS: Savisor Server Bootstrapping Complete!"
Write-Host "Base Folder: C:\savisor"
Write-Host "Orchestrator Port: 8000 (Protected & Monitored)"
Write-Host "========================================================="
