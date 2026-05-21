<#
.SYNOPSIS
    Stage, commit, and push all .gitignore-allowed changes to origin/<current-branch>.

.DESCRIPTION
    One-shot cross-machine sync entry point for EEG_Project. When the user
    says "commit" / "sync" / "push", Claude / Cursor should invoke this
    script (see CLAUDE.md "Quick commit workflow" section).

    Design principles (CLAUDE.md compatible):
      1. Hard-coded safety net rejects anything that looks like raw subject
         data ( /data/ path segment, or extensions in bdf/npz/fif/edf/mp4/
         set/cnt/vhdr/vmrk/eeg/mat ) regardless of .gitignore state.
      2. No destructive ops: never reset --hard / push --force / clean.
      3. Always pushes the CURRENT branch to origin; never switches branch.
      4. Commit message defaults to "chore(sync): <date-time> (n files)";
         pass -Message to override.

    NOTE on encoding:
      All comments/strings inside this script are pure ASCII on purpose.
      PowerShell 5.x on Chinese Windows decodes .ps1 files as GBK unless
      they carry a UTF-8 BOM; non-ASCII bytes inside the script would
      otherwise produce parse errors. The script itself, however, talks
      UTF-8 to git via ProcessStartInfo and prints UTF-8 to the console.

.PARAMETER Message
    Custom commit message. Defaults to a timestamp summary.

.PARAMETER NoPush
    Commit but skip push (offline, or when you want to review first).

.PARAMETER DryRun
    Print what would be done. Does not modify git state.

.EXAMPLE
    .\scripts\sync_to_github.ps1
    .\scripts\sync_to_github.ps1 -Message "feat: add session4 mi flow"
    .\scripts\sync_to_github.ps1 -DryRun
#>

[CmdletBinding()]
param(
    [string] $Message,
    [switch] $NoPush,
    [switch] $DryRun
)

# Do NOT set ErrorActionPreference=Stop here. Git often writes informational
# output to stderr; Stop would turn those into hard exceptions. We use
# explicit $LASTEXITCODE / .ExitCode checks instead.
$ErrorActionPreference = 'Continue'

# Force UTF-8 console IO so Chinese paths render correctly.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8

# ----- helper: invoke git via ProcessStartInfo, capture stdout/stderr SAFELY -----
# Uses async event-based reading to avoid the classic deadlock where stderr
# fills its 4 KB pipe buffer (e.g. git's "LF will be replaced by CRLF" warnings)
# while we are still blocked on stdout's ReadToEnd().
function Invoke-GitCapture {
    param([string[]] $GitArgs)
    $quoted = foreach ($a in $GitArgs) {
        if ($a -match '[\s"]') {
            '"' + ($a -replace '"', '\"') + '"'
        } else {
            $a
        }
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = 'git'
    $psi.Arguments              = ($quoted -join ' ')
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute        = $false
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding  = [System.Text.Encoding]::UTF8
    $psi.WorkingDirectory       = (Get-Location).Path

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi

    $stdoutSb = New-Object System.Text.StringBuilder
    $stderrSb = New-Object System.Text.StringBuilder
    $outAction = {
        if ($null -ne $EventArgs.Data) {
            [void]$Event.MessageData.AppendLine($EventArgs.Data)
        }
    }
    $stdoutEv = Register-ObjectEvent -InputObject $p -EventName OutputDataReceived -Action $outAction -MessageData $stdoutSb
    $stderrEv = Register-ObjectEvent -InputObject $p -EventName ErrorDataReceived  -Action $outAction -MessageData $stderrSb
    try {
        [void]$p.Start()
        $p.BeginOutputReadLine()
        $p.BeginErrorReadLine()
        $p.WaitForExit()
        # Drain any remaining queued events before unregistering.
        Start-Sleep -Milliseconds 50
    } finally {
        Unregister-Event -SourceIdentifier $stdoutEv.Name -ErrorAction SilentlyContinue
        Unregister-Event -SourceIdentifier $stderrEv.Name -ErrorAction SilentlyContinue
    }

    return [pscustomobject]@{
        Stdout   = $stdoutSb.ToString()
        Stderr   = $stderrSb.ToString()
        ExitCode = $p.ExitCode
    }
}

# ----- helper: run git with stdout/stderr going straight to console -----
# Use this for commands that produce lots of output (add / push) or where we
# only care about the exit code. Returns just the exit code.
#
# IMPORTANT: redirect stderr into stdout (2>&1) then pipe to Out-Host so that:
#   1. the user sees git's progress in real time;
#   2. neither stdout nor stderr leaks into PowerShell's pipeline, which
#      would otherwise contaminate the function's return value and make
#      the caller's "if ($exit -ne 0)" check meaningless.
function Invoke-GitPassthrough {
    param([string[]] $GitArgs)
    # In PowerShell 5.x, any line a native command writes to stderr is wrapped
    # into a System.Management.Automation.ErrorRecord and rendered as a red
    # "NativeCommandError" by the host. Git uses stderr for progress / line-
    # ending warnings / push receipts that are NOT actual failures, so we
    # unwrap each record and forward it as normal host output instead.
    & git @GitArgs 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            Write-Host $_.Exception.Message
        } else {
            Write-Host $_
        }
    }
    return $LASTEXITCODE
}

# ----- 0. resolve repo root + branch -----
$rootInfo = Invoke-GitCapture @('rev-parse', '--show-toplevel')
if ($rootInfo.ExitCode -ne 0) {
    Write-Error "Not inside a git repository."
    exit 1
}
$RepoRoot = $rootInfo.Stdout.Trim()
Set-Location $RepoRoot

$branchInfo = Invoke-GitCapture @('rev-parse', '--abbrev-ref', 'HEAD')
$Branch = $branchInfo.Stdout.Trim()
Write-Host "==> Repo: $RepoRoot"
Write-Host "==> Branch: $Branch"

# ----- 1. read porcelain status (UTF-8, no octal escaping) -----
$gitResult = Invoke-GitCapture @('-c', 'core.quotepath=false', 'status', '--porcelain=v1')
if ($gitResult.ExitCode -ne 0) {
    Write-Error ("git status failed (exit {0}): {1}" -f $gitResult.ExitCode, $gitResult.Stderr)
    exit 1
}
$porcelain = $gitResult.Stdout -split "`r?`n" | Where-Object { $_.Length -gt 0 }
if (-not $porcelain) {
    Write-Host "Working tree clean. Nothing to sync." -ForegroundColor Green
    exit 0
}

# ----- 2. parse porcelain into (code, path) records -----
$entries = @()
foreach ($line in $porcelain) {
    if ($line.Length -lt 3) { continue }
    $code = $line.Substring(0, 2)
    $path = $line.Substring(3).Trim()
    if ($path -match '^(.+?)\s+->\s+(.+)$') {
        $path = $matches[2]
    }
    $path = $path.Trim('"')
    $entries += [pscustomobject]@{ Code = $code; Path = $path }
}

# ----- 3. safety net: reject obvious raw-data paths -----
$forbiddenDirRegex = '(^|/)data(/|$)'
$forbiddenExtRegex = '\.(bdf|npz|fif|edf|mp4|set|cnt|vhdr|vmrk|eeg|mat|tmp)$'

$danger = $entries | Where-Object {
    ($_.Path -match $forbiddenDirRegex) -or ($_.Path -match $forbiddenExtRegex)
}
if ($danger) {
    Write-Host ""
    Write-Host "REFUSING TO SYNC: the following paths look like raw data / subject artifacts:" -ForegroundColor Red
    foreach ($d in $danger) {
        Write-Host ("  {0,-3} {1}" -f $d.Code, $d.Path) -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "Fix .gitignore or move the files into scratch/ before retrying." -ForegroundColor Yellow
    exit 2
}

# ----- 4. print sync plan -----
Write-Host ""
Write-Host "==> Changes to sync:" -ForegroundColor Cyan
foreach ($e in $entries) {
    Write-Host ("  {0,-3} {1}" -f $e.Code, $e.Path)
}

# ----- 5. build commit message -----
if (-not $Message) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $Message = "chore(sync): $stamp ($($entries.Count) files)"
}
Write-Host ""
Write-Host "==> commit message: $Message" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host ""
    Write-Host "[dry-run] would run: git add -A; git commit -m <above>; git push origin $Branch" -ForegroundColor Yellow
    exit 0
}

# ----- 6. stage + commit + push -----
Write-Host ""
Write-Host "==> Running git add -A ..." -ForegroundColor Cyan
$addExit = Invoke-GitPassthrough @('add', '-A')
if ($addExit -ne 0) {
    Write-Error "git add failed (exit $addExit)."
    exit 1
}

$cachedRes = Invoke-GitCapture @('diff', '--cached', '--name-only')
if (-not $cachedRes.Stdout.Trim()) {
    Write-Host "Nothing actually staged after .gitignore filtering." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "==> Running git commit ..." -ForegroundColor Cyan
$commitExit = Invoke-GitPassthrough @('commit', '-m', $Message)
if ($commitExit -ne 0) {
    Write-Error "git commit failed (exit $commitExit)."
    exit 1
}

if ($NoPush) {
    Write-Host ""
    Write-Host "Commit created. Skipping push (-NoPush)." -ForegroundColor Green
    & git log -1 --oneline
    exit 0
}

$remoteRes = Invoke-GitCapture @('remote')
if (-not $remoteRes.Stdout.Trim()) {
    Write-Host ""
    Write-Host "No git remote configured. Commit kept locally." -ForegroundColor Yellow
    Write-Host "  Add one e.g.: git remote add origin git@github.com:<user>/<repo>.git" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "==> Pushing to origin/$Branch ..." -ForegroundColor Cyan
$pushExit = Invoke-GitPassthrough @('push', '-u', 'origin', $Branch)
if ($pushExit -ne 0) {
    Write-Error ("git push failed (exit {0}). Commit is kept locally; fix network/auth then re-run." -f $pushExit)
    exit 1
}

Write-Host ""
Write-Host "Sync complete." -ForegroundColor Green
& git log -1 --oneline
