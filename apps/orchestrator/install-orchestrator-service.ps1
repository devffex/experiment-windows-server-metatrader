# Administrative PowerShell Script to Install Savisor Orchestrator as a Windows Service
# Must be run from an elevated Administrator PowerShell terminal.

# 1. Verify administrative privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "ERROR: This script must be run as an Administrator. Please run PowerShell as Administrator."
    exit 1
}

$ServiceName = "SavisorOrchestrator"
Write-Host "========================================="
Write-Host "Installing Savisor Orchestrator Service..."
Write-Host "========================================="

# 2. Determine paths
$ScriptDir = $PSScriptRoot
$WorkspaceRoot = $ScriptDir
if ($ScriptDir -match "apps[\\/]orchestrator$") {
    $WorkspaceRoot = Split-Path $ScriptDir -Parent
}

# Resolve active virtual environment Python
$PythonExe = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    # Fallback to system Python
    $PythonExe = Get-Command "python" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if (-not $PythonExe) {
        Write-Error "ERROR: Python executable not found in .venv or system PATH. Please build the project environment first."
        exit 1
    }
}
Write-Host "Using Python Executable: $PythonExe"

# 3. Locate or download nssm.exe
$NssmPath = Get-Command "nssm" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
$LocalNssm = Join-Path $ScriptDir "nssm.exe"

if (-not $NssmPath) {
    if (Test-Path $LocalNssm) {
        $NssmPath = $LocalNssm
    } else {
        Write-Host "nssm.exe not found in PATH or locally. Fetching NSSM from nssm.cc..."
        $NssmZipUrl = "https://nssm.cc/release/nssm-2.24.zip"
        $TempZip = Join-Path ([System.IO.Path]::GetTempPath()) "nssm-2.24.zip"
        $TempExtractDir = Join-Path ([System.IO.Path]::GetTempPath()) "nssm-temp"
        
        # Ensure TLS 1.2 is enabled for secure web downloads
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        
        try {
            Write-Host "Downloading $NssmZipUrl..."
            Invoke-WebRequest -Uri $NssmZipUrl -OutFile $TempZip -UseBasicParsing -ErrorAction Stop
            
            Write-Host "Extracting zip archive..."
            if (Test-Path $TempExtractDir) { Remove-Item -Path $TempExtractDir -Recurse -Force | Out-Null }
            Expand-Archive -Path $TempZip -DestinationPath $TempExtractDir -Force
            
            # Extract 64-bit NSSM
            $NssmSource = Join-Path $TempExtractDir "nssm-2.24\win64\nssm.exe"
            if (-not (Test-Path $NssmSource)) {
                # Fallback to 32-bit if 64-bit is missing
                $NssmSource = Join-Path $TempExtractDir "nssm-2.24\win32\nssm.exe"
            }
            
            if (Test-Path $NssmSource) {
                Copy-Item -Path $NssmSource -Destination $LocalNssm -Force
                $NssmPath = $LocalNssm
                Write-Host "NSSM successfully downloaded to: $LocalNssm"
            } else {
                throw "Could not locate nssm.exe inside the extracted archive."
            }
        } catch {
            Write-Error "Failed to download NSSM dynamically: $_"
            Write-Host "Please download nssm.exe manually, place it at: $LocalNssm, and run this script again."
            exit 1
        } finally {
            if (Test-Path $TempZip) { Remove-Item -Path $TempZip -Force | Out-Null }
            if (Test-Path $TempExtractDir) { Remove-Item -Path $TempExtractDir -Recurse -Force -ErrorAction SilentlyContinue | Out-Null }
        }
    }
}
Write-Host "Using NSSM Path: $NssmPath"

# 4. Remove existing service if it exists (idempotent setup)
$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host "Existing service '$ServiceName' detected. Stopping and removing..."
    & $NssmPath stop $ServiceName | Out-Null
    & $NssmPath remove $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 1
}

# 5. Install the service
Write-Host "Registering service '$ServiceName'..."
$AppArguments = "-m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000"
$AppDirectory = Join-Path $WorkspaceRoot "apps\orchestrator\src"

& $NssmPath install $ServiceName $PythonExe $AppArguments
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install service using NSSM."
    exit 1
}

# Configure AppDirectory
& $NssmPath set $ServiceName AppDirectory $AppDirectory

# Setup Logging Directories & Paths
$LogDir = "C:\savisor\logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}
$StdoutLog = Join-Path $LogDir "orchestrator.log"
$StderrLog = Join-Path $LogDir "orchestrator-error.log"

# Configure logging outputs and rotation
& $NssmPath set $ServiceName AppStdout $StdoutLog
& $NssmPath set $ServiceName AppStderr $StderrLog
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateOnline 1
& $NssmPath set $ServiceName AppRotateBytes 10485760 # 10 MB limit
& $NssmPath set $ServiceName AppRotateBackups 5

# Set startup behavior and failure recovery
& $NssmPath set $ServiceName Start SERVICE_AUTO_START
& $NssmPath set $ServiceName AppThrottle 1000  # Pause 1 second before restarting on failure
& $NssmPath set $ServiceName AppEnvironmentExtra "PYTHONIOENCODING=utf-8"

# 6. Start the Service
Write-Host "Starting service '$ServiceName'..."
& $NssmPath start $ServiceName

$status = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($status -and $status.Status -eq "Running") {
    Write-Host "========================================="
    Write-Host "SUCCESS: Savisor Orchestrator is running!"
    Write-Host "Logs: $StdoutLog"
    Write-Host "Errors: $StderrLog"
    Write-Host "========================================="
} else {
    Write-Warning "WARNING: Service was created, but status is '$($status.Status)'."
    Write-Warning "Please check the error logs at: $StderrLog"
}
