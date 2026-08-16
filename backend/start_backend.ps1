# Start the backend with OpenTelemetry disabled to suppress telemetry warnings
# Usage: Run this script from PowerShell (ExecutionPolicy may need to allow running scripts)

try {
	# Disable OpenTelemetry auto-instrumentation for this process
	$env:OTEL_PYTHON_DISABLED = "1"

	# Determine paths
	$backendDir = $PSScriptRoot
	$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
	$logsDir = Join-Path $projectRoot "logs"
	if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }
	$backendLog = Join-Path $logsDir "backend.log"
	$backendErr = Join-Path $logsDir "backend.err"
	$pidFile = Join-Path $backendDir "backend.pid"

	# Move to the backend folder
	Set-Location -Path $backendDir

	# Activate the project virtual environment (relative path)
	$activate = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
	if (Test-Path $activate) {
		. $activate
	} else {
		Write-Output "Warning: virtualenv activation script not found at $activate"
	}

	# Start uvicorn and redirect output to the project logs/backend.log
	Write-Output "Starting backend (uvicorn). Logs -> $backendLog"
	$args = "app:app --host 127.0.0.1 --port 8000 --reload"
	$proc = Start-Process -FilePath "uvicorn" -ArgumentList $args -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr -PassThru

	# Save PID for convenience
	$proc.Id | Out-File -FilePath $pidFile -Encoding ascii
	Write-Output "Backend started (pid $($proc.Id)), pid file: $pidFile"
} catch {
	Write-Error "Failed to start backend: $_"
	exit 1
}
