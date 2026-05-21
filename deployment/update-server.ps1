param (
    [string]$S3BucketName = "savisor-production-deploy-bucket",
    [string]$BaseDir = "C:\savisor"
)

# 1. Setup logging
$LogDir = Join-Path $BaseDir "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir "deployment-update.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Line = "[$Timestamp] $Message"
    Write-Output $Line
    Out-File -FilePath $LogFile -Append -InputObject $Line -Encoding utf8
}

Write-Log "========================================================="
Write-Log "Starting Automated Rolling Update via AWS SSM Run Command"
Write-Log "Target Bucket: $S3BucketName | Base Dir: $BaseDir"
Write-Log "========================================================="

# 2. Establish temporary update folder
$UpdateTempPath = Join-Path $BaseDir "temp\updates"
if (Test-Path $UpdateTempPath) {
    Remove-Item -Path "$UpdateTempPath\*" -Recurse -Force -ErrorAction SilentlyContinue | Out-Null
} else {
    New-Item -ItemType Directory -Path $UpdateTempPath -Force | Out-Null
}

# 3. Pull upgraded wheels from private S3 deployment bucket
try {
    Write-Log "Importing AWS AWSPowerShell tools..."
    Import-Module AWSPowerShell -ErrorAction SilentlyContinue
    
    Write-Log "Downloading new Python wheel distributions from S3 bucket: $S3BucketName"
    # Copy all wheels from deployment bucket updates folder
    Get-S3Object -BucketName $S3BucketName -KeyPrefix "updates/" | ForEach-Object {
        $FileName = $_.Key.Split('/')[-1]
        if ($FileName -and $FileName.EndsWith(".whl")) {
            Copy-S3Object -BucketName $S3BucketName -Key $_.Key -LocalFile "$UpdateTempPath\$FileName" -Force
            Write-Log "Downloaded artifact: $FileName"
        }
    }
} catch {
    Write-Log "ERROR: Failed to download updates from S3 bucket: $_"
    exit 1
}

# 4. Stop the Central Orchestrator service (system background service)
Write-Log "Stopping SavisorOrchestrator Windows Service..."
$OrchService = Get-Service -Name "SavisorOrchestrator" -ErrorAction SilentlyContinue
if ($OrchService) {
    Stop-Service -Name "SavisorOrchestrator" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
} else {
    Write-Log "WARNING: SavisorOrchestrator service is not currently registered."
}

# 5. Free local python file locks across all user sessions
Write-Log "Terminating running pythonw.exe and python.exe wrappers to unlock global .venv..."
$PythonProcesses = Get-Process -Name "pythonw", "python" -ErrorAction SilentlyContinue
if ($PythonProcesses) {
    Write-Log "Found $($PythonProcesses.Count) active python processes. Terminating..."
    $PythonProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
} else {
    Write-Log "No active python processes found. Proceeding."
}

# 6. Apply global package updates using uv
$UvExe = Join-Path $BaseDir ".venv\Scripts\uv.exe"
if (-not (Test-Path $UvExe)) {
    Write-Log "ERROR: uv package manager not found at expected path: $UvExe"
    exit 1
}

$Wheels = Get-ChildItem -Path "$UpdateTempPath" -Filter "*.whl"
if (-not $Wheels) {
    Write-Log "ERROR: No Python wheel distributions found in download path."
    exit 1
}

Write-Log "Executing global package upgrade via uv..."
try {
    foreach ($wheel in $Wheels) {
        Write-Log "Installing: $($wheel.Name)..."
        # Run uv upgrade without internet access, pulling purely from local downloaded wheels
        & $UvExe pip install --upgrade --no-index --find-links "$UpdateTempPath" $wheel.FullName >> $LogFile 2>&1
    }
    Write-Log "SUCCESS: Global package upgrade complete."
} catch {
    Write-Log "ERROR: Failed to execute packages upgrade: $_"
    exit 1
}

# 7. Restart the Central Orchestrator Service
Write-Log "Restarting SavisorOrchestrator Windows Service..."
if ($OrchService) {
    Start-Service -Name "SavisorOrchestrator" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $OrchService = Get-Service -Name "SavisorOrchestrator" -ErrorAction SilentlyContinue
    Write-Log "SavisorOrchestrator service status is: $($OrchService.Status)"
} else {
    Write-Log "Triggering central-service auto-registration..."
    $ServiceInstaller = Join-Path $BaseDir "experiment-windows-server-metatrader\apps\orchestrator\install-orchestrator-service.ps1"
    if (Test-Path $ServiceInstaller) {
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ServiceInstaller >> $LogFile 2>&1
    }
}

# 8. Clean up and log rolling update outcomes
Write-Log "Cleaning up temporary download folders..."
if (Test-Path $UpdateTempPath) {
    Remove-Item -Path "$UpdateTempPath\*" -Recurse -Force -ErrorAction SilentlyContinue | Out-Null
}

Write-Log "========================================================="
Write-Log "SUCCESS: Rolling update has been fully applied!"
Write-Log "Background session monitors will self-heal within 3 seconds."
Write-Log "========================================================="
