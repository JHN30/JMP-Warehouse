<#
.SYNOPSIS
Register, update or remove the daily 06:00 current-season refresh task.

.DESCRIPTION
Creates one Windows Task Scheduler task for the current user that runs
python pipeline.py from this folder every day at 06:00, only while the user is
logged on (no stored password, no admin rights). A start missed because the
laptop was off or asleep runs as soon as possible afterwards. Each run publishes
the current season to Neon live, so a registered task is the owner's standing
approval for that publish; -Remove withdraws it. Running the script again
replaces the task with the same definition. It never starts the task.

    powershell -ExecutionPolicy Bypass -File register_refresh_task.ps1
    powershell -ExecutionPolicy Bypass -File register_refresh_task.ps1 -Remove
#>
param([switch]$Remove)

$ErrorActionPreference = "Stop"
$TaskName = "JMP Warehouse refresh"
$TaskPath = "\"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
        Write-Output "Removed scheduled task '$TaskName'."
    } else {
        Write-Output "Scheduled task '$TaskName' is not registered."
    }
    exit 0
}

$python = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $python) {
    Write-Output "python was not found on PATH; install Python 3.13 or activate its environment first."
    exit 1
}
if ($python.Source -like "*\WindowsApps\*") {
    Write-Output "python resolves to the Microsoft Store stub ($($python.Source)); put the real Python 3.13 first on PATH."
    exit 1
}

# Standard input is an empty pipe, not the hidden console, so pipeline.py never
# waits at its Neon URL prompt. The task's Last Run Result is pipeline.py's exit code,
# or 1 when Python could not be started (for example its stored path no longer exists).
$command = "@() | & '{0}' pipeline.py; if (`$null -eq `$LASTEXITCODE) {{ exit 1 }}; exit `$LASTEXITCODE" -f ($python.Source -replace "'", "''")
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"$command`"" -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "06:00"
# Without a time-zone offset the start time follows the local clock, so the run stays
# at 06:00 across daylight saving changes instead of being pinned to one UTC time.
# Starting at the next 06:00 keeps a re-registration after 06:00 from counting as a
# missed start and publishing at once. "s" is the same in every culture.
$start = Get-Date "06:00"
if ($start -le (Get-Date)) { $start = $start.AddDays(1) }
$trigger.StartBoundary = $start.ToString("s")
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description "Daily current-season refresh: python pipeline.py (fetch, load, quality checks, live Neon publish)." |
    Out-Null

$info = Get-ScheduledTaskInfo -TaskName $TaskName -TaskPath $TaskPath
Write-Output "Registered scheduled task '$TaskName' for $user."
Write-Output "  Python:   $($python.Source)"
Write-Output "  Folder:   $PSScriptRoot"
Write-Output "  Next run: $($info.NextRunTime)"
