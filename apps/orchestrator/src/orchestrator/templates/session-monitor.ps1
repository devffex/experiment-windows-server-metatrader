param (
    [Parameter(Mandatory=$true)]
    [string]$Username,
    [Parameter(Mandatory=$true)]
    [int]$Port,
    [string]$BaseDir = "C:\savisor",
    [string]$TerminalDir = "C:\savisor\terminal",
    [string]$PythonExe = ""
)

# Helper to ensure directories exist
function Ensure-Directory {
    param([string]$Path)
    if (!(Test-Path $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

# Setup logging
$LogDir = Join-Path $BaseDir "logs"
Ensure-Directory $LogDir
$LogFile = Join-Path $LogDir "session-monitor-$Username.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Line = "[$Timestamp] $Message"
    Write-Output $Line
    Out-File -FilePath $LogFile -Append -InputObject $Line -Encoding utf8
}

Write-Log "========================================="
Write-Log "Savisor Session Monitor Started for user: $Username"
Write-Log "Parameters: Port=$Port, BaseDir=$BaseDir, TerminalDir=$TerminalDir"

# Resolve pythonw.exe or python.exe
if ([string]::IsNullOrEmpty($PythonExe)) {
    $possiblePaths = @(
        "$BaseDir\.venv\Scripts\pythonw.exe",
        "$BaseDir\experiment-windows-server-metatrader\.venv\Scripts\pythonw.exe",
        "C:\Users\julio\Savisor\experiment-windows-server-metatrader\.venv\Scripts\pythonw.exe",
        "$BaseDir\.venv\Scripts\python.exe",
        "pythonw.exe",
        "python.exe"
    )
    foreach ($path in $possiblePaths) {
        if ($path -eq "pythonw.exe" -or $path -eq "python.exe" -or (Test-Path $path)) {
            $PythonExe = $path
            break
        }
    }
}
Write-Log "Resolved python executable to: $PythonExe"

# Launch the API wrapper
Write-Log "Starting session-wrapper API on port $Port..."
$ApiArguments = "-m session_wrapper.main --port=$Port"
$ApiProcess = Start-Process -FilePath $PythonExe -ArgumentList $ApiArguments -WorkingDirectory $BaseDir -PassThru -NoNewWindow
if ($ApiProcess) {
    Write-Log "Session-wrapper API started with PID $($ApiProcess.Id)."
} else {
    Write-Log "Failed to start session-wrapper API."
}

# Launch MetaTrader 5 portable terminal
Write-Log "Starting MetaTrader 5 portable terminal..."
$TerminalPath = Join-Path $TerminalDir "terminal64.exe"
$Mt5Process = $null

if (Test-Path $TerminalPath) {
    $Mt5Process = Start-Process -FilePath $TerminalPath -ArgumentList "/portable" -WorkingDirectory $TerminalDir -PassThru -NoNewWindow
    if ($Mt5Process) {
        Write-Log "MetaTrader 5 started with PID $($Mt5Process.Id)."
    } else {
        Write-Log "Failed to start MetaTrader 5 process."
    }
} else {
    Write-Log "ERROR: MetaTrader 5 executable not found at: $TerminalPath"
}

# Get current Session ID
$CurrentSessionId = (Get-Process -Id $PID).SessionId
Write-Log "Current Windows Session ID: $CurrentSessionId"

# Enter process supervision loop
Write-Log "Entering process supervision loop..."
$LoopIntervalSeconds = 3

while ($true) {
    Start-Sleep -Seconds $LoopIntervalSeconds

    # 1. Monitor MetaTrader 5 status
    $mt5Running = $false
    if ($null -ne $Mt5Process) {
        try {
            if (-not $Mt5Process.HasExited) {
                $mt5Running = $true
            }
        } catch {
            # Handle edge cases where process handle might become stale or lack permission
        }
    }
    
    # Fallback/Additional check: check for any terminal64 process in this interactive RDP session
    if (-not $mt5Running) {
        $sessionMt5 = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $CurrentSessionId }
        if ($sessionMt5) {
            $mt5Running = $true
            # Recover the process handle if we lost it
            $Mt5Process = $sessionMt5[0]
        }
    }

    if (-not $mt5Running) {
        Write-Log "MetaTrader 5 terminal is no longer running in Session $CurrentSessionId. Initiating shutdown..."
        break
    }

    # 2. Monitor Session-Wrapper API status
    $apiRunning = $false
    if ($null -ne $ApiProcess) {
        try {
            if (-not $ApiProcess.HasExited) {
                $apiRunning = $true
            }
        } catch {}
    }

    # Recover API process handle if needed by checking for python/pythonw running in this Session
    if (-not $apiRunning) {
        $sessionApis = Get-Process -Name "pythonw", "python" -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $CurrentSessionId }
        if ($sessionApis) {
            $apiRunning = $true
            $ApiProcess = $sessionApis[0]
        }
    }

    # Self-healing check: if API wrapper has crashed/stopped, restart it
    if (-not $apiRunning) {
        Write-Log "WARNING: Session-wrapper API has exited unexpectedly! Self-healing triggered. Restarting API..."
        $ApiProcess = Start-Process -FilePath $PythonExe -ArgumentList $ApiArguments -WorkingDirectory $BaseDir -PassThru -NoNewWindow
        if ($ApiProcess) {
            Write-Log "Session-wrapper API successfully restarted with PID $($ApiProcess.Id)."
        } else {
            Write-Log "ERROR: Failed to restart session-wrapper API."
        }
    }
}

# Cleanup on exit
Write-Log "Cleaning up session background processes..."

if ($null -ne $ApiProcess) {
    try {
        if (-not $ApiProcess.HasExited) {
            Write-Log "Stopping session-wrapper API process (PID $($ApiProcess.Id))..."
            Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

# Sweep and terminate any remaining python/pythonw processes in this session to prevent orphan ports
Write-Log "Sweeping any orphan python processes in Session $CurrentSessionId..."
Get-Process -Name "pythonw", "python" -ErrorAction SilentlyContinue | 
    Where-Object { $_.SessionId -eq $CurrentSessionId -and $_.Id -ne $PID } | 
    Stop-Process -Force -ErrorAction SilentlyContinue

Write-Log "Savisor Session Monitor finished. Invoking logoff..."
Write-Log "========================================="
Start-Sleep -Seconds 1
& logoff
