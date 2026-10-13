# Daily ingest with Windows Task Scheduler (docs/web-ui.md W14, docs/ingest.md I6).
#
# Registers the task "rmprep daily ingest" for the current user: every day at
# 07:30 it runs `python -m rmprep ingest` in prototype/ and appends the output to
# data/logs/ingest.log. "StartWhenAvailable": a start that was missed (laptop off
# or asleep) runs as soon as the laptop is on again. The ingest lock (I6) stops a
# second ingest while one runs (for example the "Veriyi yenile" button).
#
# Usage (PowerShell, in prototype/):
#   .\scripts\schedule_ingest.ps1                 # register or update the task
#   .\scripts\schedule_ingest.ps1 -At 08:00       # another time
#   .\scripts\schedule_ingest.ps1 -WakeToRun      # also wake the laptop from sleep
#   .\scripts\schedule_ingest.ps1 -Remove         # delete the task
#   Start-ScheduledTask -TaskName "rmprep daily ingest"   # run it now once

param(
    [string]$At = "07:30",
    [switch]$WakeToRun,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$TaskName = "rmprep daily ingest"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Removed the task '$TaskName'."
    return
}

$Root = Split-Path -Parent $PSScriptRoot          # prototype/
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "No virtual environment: $Python" }
$Log = Join-Path $Root "data\logs\ingest.log"

# run_ingest.cmd writes the start time, the ingest output and the exit code to the log.
$Runner = Join-Path $PSScriptRoot "run_ingest.cmd"
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Runner`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew -WakeToRun:$WakeToRun

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "rmprep: daily ingest of EVDS, TEFAS and the manual inbox (ING hackathon prototype)" `
    -Force | Out-Null
Write-Output "Registered '$TaskName': daily at $At, log $Log."
