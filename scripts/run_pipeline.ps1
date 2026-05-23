<#
.SYNOPSIS
    P4 EEG processing pipeline launcher (interactive + scriptable).

.DESCRIPTION
    One-stop entry point to drive P4_EEG/processing/pipeline. Handles:
      - locating the eeg-p4 conda env (no need to `conda activate` first)
      - setting UTF-8 console / PYTHONIOENCODING so Chinese output renders
      - menu-driven workflow for everyday use
      - direct -Action flags for scripting / CI
      - auto-opening the QC HTML report when a run finishes

    NOTE on encoding:
      Body of this script is pure ASCII on purpose. PowerShell 5.x on a
      Chinese Windows decodes .ps1 as GBK unless the file carries a UTF-8
      BOM; mixing non-ASCII text inside the script body would otherwise
      hit parse errors on older shells. UTF-8 is enabled only for I/O
      with python child processes via PYTHONIOENCODING.

.PARAMETER Action
    Skip the menu and run a specific action:
      scan    - dry-run, list BDF<->NPZ pairing only (read-only, safest)
      pick    - interactively pick which recording (subject+date) to process
      run     - run full pipeline; combine with -Subject / -Date to restrict
      synth   - generate synthetic data + run pipeline (no real data)
      clean   - delete derivatives dir so next run starts fresh
      open    - open the most recent QC HTML report
      help    - print usage

.PARAMETER Subject
    Restrict `run` to a single subject id (e.g. Sub_01).

.PARAMETER Date
    Restrict `run` to a single recording day. Format: YYYYMMDD (e.g. 20260521).
    When set, outputs go to ...derivatives/<subject>/05_qc/report_<date>.html
    so different days do not overwrite each other.

.PARAMETER Force
    Pass through to pipeline: overwrite existing derivatives outputs.

.PARAMETER Scheme
    Experiment scheme: 'motor_imagery' (default) or 'emotion'. Drives the
    default data dir / out dir if those are not explicitly overridden.

.PARAMETER DataDir
    Override data dir. Default: ../P4_EEG.../experiment/data/<scheme>

.PARAMETER OutDir
    Override out dir. Default: ../P4_EEG.../derivatives/<scheme>

.EXAMPLE
    .\scripts\run_pipeline.ps1
        Interactive menu (recommended for daily use).

.EXAMPLE
    .\scripts\run_pipeline.ps1 -Action pick
        Scan data, list available recordings, prompt you to pick one.

.EXAMPLE
    .\scripts\run_pipeline.ps1 -Action run -Subject Sub_01 -Date 20260521
        Process just today's recording for Sub_01 (non-interactive).

.EXAMPLE
    .\scripts\run_pipeline.ps1 -Action scan
        Just print the BDF<->NPZ pairing table and exit.

.EXAMPLE
    .\scripts\run_pipeline.ps1 -Action synth
        Smoke-test the pipeline on synthetic data (touches no real data).
#>

[CmdletBinding()]
param(
    [ValidateSet('menu','scan','pick','run','synth','clean','open','help')]
    [string]$Action = 'menu',
    [ValidateSet('motor_imagery','emotion')]
    [string]$Scheme = 'motor_imagery',
    [string]$Subject = '',
    [string]$Date = '',
    [switch]$Force,
    [string]$DataDir = '',
    [string]$OutDir = ''
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$ProjectDir = Join-Path $RepoRoot 'P4_EEG_____________________' # fallback name with placeholder

# The project dir name is Chinese; find it via wildcard rather than literal.
$ProjectDir = (Get-ChildItem -Path $RepoRoot -Directory |
               Where-Object { $_.Name -like 'P4_EEG*' } |
               Select-Object -First 1).FullName
if (-not $ProjectDir) {
    Write-Host "[fail] Cannot locate P4_EEG* directory under repo root: $RepoRoot" -ForegroundColor Red
    exit 1
}

$ProcessingDir = Join-Path $ProjectDir 'processing'
# Data and derivatives are now split per scheme so MI and Emotion runs
# do not overwrite each other. Defaults derive from -Scheme; explicit
# -DataDir / -OutDir still override.
$DefaultDataDir = Join-Path $ProjectDir ("experiment/data/" + $Scheme)
$DefaultOutDir = Join-Path $ProjectDir ("derivatives/" + $Scheme)
$ScratchDir = Join-Path $RepoRoot 'scratch'
$SynthDataDir = Join-Path $ScratchDir 'synth_data'
$SynthOutDir = Join-Path $ScratchDir 'synth_derivatives'

if (-not $DataDir) { $DataDir = $DefaultDataDir }
if (-not $OutDir)  { $OutDir  = $DefaultOutDir  }

# ---------------------------------------------------------------------------
# Console encoding (so Python's Chinese output is not garbled)
# ---------------------------------------------------------------------------
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

# ---------------------------------------------------------------------------
# Locate the eeg-p4 conda env Python
# ---------------------------------------------------------------------------
function Find-EegPyExe {
    $candidates = @(
        (Join-Path $env:USERPROFILE 'miniconda3/envs/eeg-p4/python.exe'),
        (Join-Path $env:USERPROFILE 'anaconda3/envs/eeg-p4/python.exe'),
        'C:/ProgramData/miniconda3/envs/eeg-p4/python.exe',
        'C:/ProgramData/anaconda3/envs/eeg-p4/python.exe'
    )
    foreach ($p in $candidates) {
        $p = $p -replace '/', '\'
        if (Test-Path $p) { return $p }
    }
    # Last resort: try `conda` on PATH.
    $conda = (Get-Command conda -ErrorAction SilentlyContinue)
    if ($conda) {
        $envs = & conda env list 2>$null | Where-Object { $_ -match 'eeg-p4' }
        if ($envs) {
            $envPath = ($envs -split '\s+' | Where-Object { $_ -like '*envs*eeg-p4' } | Select-Object -First 1)
            if ($envPath) {
                $cand = Join-Path $envPath 'python.exe'
                if (Test-Path $cand) { return $cand }
            }
        }
    }
    return $null
}

$PyExe = Find-EegPyExe
if (-not $PyExe) {
    Write-Host "[fail] Cannot find eeg-p4 conda env python.exe." -ForegroundColor Red
    Write-Host "       Expected one of:" -ForegroundColor Yellow
    Write-Host "         $env:USERPROFILE\miniconda3\envs\eeg-p4\python.exe" -ForegroundColor Yellow
    Write-Host "         $env:USERPROFILE\anaconda3\envs\eeg-p4\python.exe"  -ForegroundColor Yellow
    Write-Host "       Activate or create the env first:"                    -ForegroundColor Yellow
    Write-Host "         conda env create -f environment.yml"                -ForegroundColor Yellow
    Write-Host "         conda activate eeg-p4"                              -ForegroundColor Yellow
    exit 1
}

# ---------------------------------------------------------------------------
# Pretty header
# ---------------------------------------------------------------------------
function Show-Banner {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host '  P4 EEG Pipeline Launcher' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host ("  Project dir : {0}" -f $ProjectDir)
    Write-Host ("  Scheme      : {0}" -f $Scheme)
    Write-Host ("  Data dir    : {0}" -f $DataDir)
    Write-Host ("  Out dir     : {0}" -f $OutDir)
    Write-Host ("  Python      : {0}" -f $PyExe)
    Write-Host ''
}

# Script-scope exit-code tracker. PowerShell functions that `return` would
# otherwise also capture all pipeline output (including child-process stdout)
# as their return value, which silently eats Python's prints. We instead let
# Python stream straight to the host and stash the exit code here.
$script:LastActionExitCode = 0

# ---------------------------------------------------------------------------
# Action: scan (dry-run)
# ---------------------------------------------------------------------------
function Invoke-Scan {
    Write-Host '[scan] dry-run: scanning data/ and pairing BDF <-> NPZ ...' -ForegroundColor Green
    Push-Location $ProcessingDir
    try {
        & $PyExe -m pipeline.run_pipeline `
            --dry-run `
            --data-dir $DataDir `
            --out-dir  $OutDir
        $script:LastActionExitCode = $LASTEXITCODE
    } finally { Pop-Location }
}

# ---------------------------------------------------------------------------
# Action: run (full pipeline, with optional -Subject / -Date filters)
# ---------------------------------------------------------------------------
function Invoke-Run {
    if (-not (Test-Path $DataDir)) {
        Write-Host "[fail] Data dir does not exist: $DataDir" -ForegroundColor Red
        $script:LastActionExitCode = 2
        return
    }
    $label = '[run] full pipeline'
    if ($Subject) { $label += " subject=$Subject" }
    if ($Date)    { $label += " date=$Date" }
    if ($Force)   { $label += " (force)" }
    Write-Host "$label ..." -ForegroundColor Green

    $py_args = @('-m','pipeline.run_pipeline',
                 '--data-dir', $DataDir,
                 '--out-dir',  $OutDir)
    if ($Subject) { $py_args += @('--subject', $Subject) }
    if ($Date)    { $py_args += @('--date',    $Date) }
    if ($Force)   { $py_args += '--force' }

    Push-Location $ProcessingDir
    try {
        & $PyExe @py_args
        $script:LastActionExitCode = $LASTEXITCODE
    } finally { Pop-Location }

    if ($script:LastActionExitCode -eq 0) {
        Write-Host ''
        Write-Host '[run] done.' -ForegroundColor Green
        # If we ran with -Date, open that specific report directly.
        if ($Subject -and $Date) {
            $dated = Join-Path $OutDir (Join-Path $Subject "05_qc/report_$Date.html")
            if (Test-Path $dated) {
                Write-Host ("[run] QC report: {0}" -f $dated)
                try { Start-Process $dated } catch {}
                return
            }
        }
        Invoke-Open
    } else {
        Write-Host ''
        Write-Host ("[run] exited with code {0}" -f $script:LastActionExitCode) -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# Action: pick (interactive: list recordings, pick one, run it)
# ---------------------------------------------------------------------------
function Get-AvailableRuns {
    # Calls python --list-runs and parses RUN| lines.
    # Why ProcessStartInfo instead of `& $PyExe ... 2>$null`: PowerShell 5
    # wraps every line written to stderr by a native command into an
    # ErrorRecord, which pollutes stdout capture and confuses parsing. Using
    # ProcessStartInfo lets us read stdout and stderr as plain strings.
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName  = $PyExe
    $pinfo.Arguments = @(
        '-m','pipeline.run_pipeline',
        '--list-runs',
        '--data-dir', ('"' + $DataDir + '"'),
        '--out-dir',  ('"' + $OutDir  + '"')
    ) -join ' '
    $pinfo.WorkingDirectory       = $ProcessingDir
    $pinfo.UseShellExecute        = $false
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError  = $true
    $pinfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $pinfo.StandardErrorEncoding  = [System.Text.Encoding]::UTF8
    $pinfo.CreateNoWindow         = $true
    # Inherit our UTF-8 env settings into the child.
    $pinfo.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $pinfo.EnvironmentVariables['PYTHONUTF8']      = '1'

    $proc = [System.Diagnostics.Process]::Start($pinfo)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    $script:LastActionExitCode = $proc.ExitCode

    if ($script:LastActionExitCode -ne 0) {
        Write-Host '[pick] --list-runs failed. Python stderr:' -ForegroundColor Red
        Write-Host $stderr -ForegroundColor Red
        return @()
    }

    $runs = @()
    foreach ($line in ($stdout -split "`r?`n")) {
        if ($line.StartsWith('RUN|')) {
            $parts = $line -split '\|'
            if ($parts.Count -ge 6) {
                $runs += [PSCustomObject]@{
                    Subject = $parts[1]
                    Date    = $parts[2]
                    Time    = $parts[3]
                    Count   = [int]$parts[4]
                    Kinds   = $parts[5]
                }
            }
        }
    }
    return ,$runs
}

function Invoke-Pick {
    if (-not (Test-Path $DataDir)) {
        Write-Host "[fail] Data dir does not exist: $DataDir" -ForegroundColor Red
        $script:LastActionExitCode = 2
        return
    }
    Write-Host '[pick] scanning data ...' -ForegroundColor Green
    $runs = Get-AvailableRuns
    if ($null -eq $runs -or $runs.Count -eq 0) {
        Write-Host '[pick] no recordings found. Run a session first.' -ForegroundColor Yellow
        $script:LastActionExitCode = 1
        return
    }

    Write-Host ''
    Write-Host '  Available recordings:' -ForegroundColor Cyan
    Write-Host '  ----------------------------------------------------------------'
    Write-Host '   #   subject       date         time      n   sessions'
    Write-Host '  ----------------------------------------------------------------'
    for ($i = 0; $i -lt $runs.Count; $i++) {
        $r = $runs[$i]
        $dateFmt = "{0}-{1}-{2}" -f $r.Date.Substring(0,4), $r.Date.Substring(4,2), $r.Date.Substring(6,2)
        $timeFmt = "{0}:{1}:{2}" -f $r.Time.Substring(0,2), $r.Time.Substring(2,2), $r.Time.Substring(4,2)
        Write-Host ("  [{0,2}] {1,-13} {2}   {3}   {4,2}   {5}" -f ($i+1), $r.Subject, $dateFmt, $timeFmt, $r.Count, $r.Kinds)
    }
    Write-Host '  ----------------------------------------------------------------'
    Write-Host ''
    $choice = Read-Host '  Pick a number (blank to cancel)'
    if (-not $choice) {
        Write-Host '[pick] cancelled.' -ForegroundColor Yellow
        $script:LastActionExitCode = 0
        return
    }
    if (-not [int]::TryParse($choice, [ref]$null)) {
        Write-Host "[pick] not a number: $choice" -ForegroundColor Yellow
        $script:LastActionExitCode = 1
        return
    }
    $idx = [int]$choice - 1
    if ($idx -lt 0 -or $idx -ge $runs.Count) {
        Write-Host "[pick] out of range: $choice" -ForegroundColor Yellow
        $script:LastActionExitCode = 1
        return
    }
    $pick = $runs[$idx]

    # Pre-flight: check if outputs already exist for this run, offer force-rebuild.
    $existingQc = Join-Path $OutDir (Join-Path $pick.Subject "05_qc/report_$($pick.Date).html")
    $askForce = $false
    if (Test-Path $existingQc) {
        Write-Host ''
        Write-Host ("  [info] outputs already exist: {0}" -f $existingQc) -ForegroundColor Yellow
        $ans = Read-Host '  Re-process and overwrite? [y/N]'
        if ($ans -match '^[yY]') { $askForce = $true }
        else {
            Write-Host '[pick] keeping existing outputs; opening report.' -ForegroundColor Yellow
            try { Start-Process $existingQc } catch {}
            $script:LastActionExitCode = 0
            return
        }
    }

    # Delegate to Invoke-Run with the picked subject/date.
    $script:Subject = $pick.Subject
    $script:Date    = $pick.Date
    if ($askForce) { $script:Force = [switch]::Present }
    Invoke-Run
}

# ---------------------------------------------------------------------------
# Action: synth (smoke test on synthetic data)
# ---------------------------------------------------------------------------
function Invoke-Synth {
    Write-Host '[synth] generating synthetic EDF + NPZ in scratch/synth_data/ ...' -ForegroundColor Green
    $synthScript = Join-Path $ProcessingDir 'tests/make_synth_data.py'
    if (-not (Test-Path $synthScript)) {
        Write-Host "[fail] missing: $synthScript" -ForegroundColor Red
        $script:LastActionExitCode = 2
        return
    }
    & $PyExe $synthScript
    $script:LastActionExitCode = $LASTEXITCODE
    if ($script:LastActionExitCode -ne 0) { return }

    Write-Host ''
    Write-Host '[synth] running pipeline on synthetic data ...' -ForegroundColor Green
    Push-Location $ProcessingDir
    try {
        & $PyExe -m pipeline.run_pipeline `
            --data-dir $SynthDataDir `
            --out-dir  $SynthOutDir `
            --force
        $script:LastActionExitCode = $LASTEXITCODE
    } finally { Pop-Location }

    if ($script:LastActionExitCode -eq 0) {
        Write-Host ''
        Write-Host '[synth] success. QC report:' -ForegroundColor Green
        $qc = Join-Path $SynthOutDir 'Synth_01/05_qc/report.html'
        if (Test-Path $qc) {
            Write-Host "  $qc"
            try { Start-Process $qc } catch {}
        }
    }
}

# ---------------------------------------------------------------------------
# Action: clean
# ---------------------------------------------------------------------------
function Invoke-Clean {
    if (-not (Test-Path $OutDir)) {
        Write-Host ("[clean] out dir does not exist, nothing to do: {0}" -f $OutDir) -ForegroundColor Yellow
        $script:LastActionExitCode = 0
        return
    }
    Write-Host ("[clean] about to delete: {0}" -f $OutDir) -ForegroundColor Yellow
    $confirm = Read-Host "  Type 'yes' to confirm"
    if ($confirm -ne 'yes') {
        Write-Host "[clean] cancelled." -ForegroundColor Yellow
        $script:LastActionExitCode = 0
        return
    }
    Remove-Item -LiteralPath $OutDir -Recurse -Force
    Write-Host ("[clean] removed {0}" -f $OutDir) -ForegroundColor Green
    $script:LastActionExitCode = 0
}

# ---------------------------------------------------------------------------
# Action: open (open most recent QC report)
# ---------------------------------------------------------------------------
function Invoke-Open {
    $reports = @()
    foreach ($root in @($OutDir, $SynthOutDir)) {
        if (Test-Path $root) {
            $reports += Get-ChildItem -Path $root -Recurse -Filter 'report.html' -ErrorAction SilentlyContinue
        }
    }
    if ($reports.Count -eq 0) {
        Write-Host "[open] no QC report found yet. Run the pipeline first." -ForegroundColor Yellow
        $script:LastActionExitCode = 1
        return
    }
    $latest = $reports | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Write-Host ("[open] opening: {0}" -f $latest.FullName) -ForegroundColor Green
    try {
        Start-Process $latest.FullName
    } catch {
        Write-Host ("[open] failed to open: {0}" -f $_) -ForegroundColor Red
        $script:LastActionExitCode = 1
        return
    }
    $script:LastActionExitCode = 0
}

# ---------------------------------------------------------------------------
# Action: help
# ---------------------------------------------------------------------------
function Show-Help {
    Get-Help $PSCommandPath -Detailed
}

# ---------------------------------------------------------------------------
# Action: menu
# ---------------------------------------------------------------------------
function Invoke-Menu {
    while ($true) {
        Write-Host '  Choose an action:' -ForegroundColor Cyan
        Write-Host '    1. Scan data (dry-run, BDF/NPZ pairing, read-only)'
        Write-Host '    2. Pick & process a single recording  [recommended]'
        Write-Host '    3. Process EVERYTHING (all subjects, all dates)'
        Write-Host '    4. Synth smoke test (no real data touched)'
        Write-Host '    5. Open most recent QC report'
        Write-Host '    6. Clean derivatives dir'
        Write-Host '    0. Exit'
        Write-Host ''
        $choice = Read-Host '  Enter choice [0-6]'
        Write-Host ''
        switch ($choice) {
            '1' { Invoke-Scan  }
            '2' {
                # Reset any leftover scope state from previous iterations.
                $script:Subject = ''
                $script:Date    = ''
                $script:Force   = [switch]$false
                Invoke-Pick
            }
            '3' {
                $script:Subject = ''
                $script:Date    = ''
                Invoke-Run
            }
            '4' { Invoke-Synth }
            '5' { Invoke-Open  }
            '6' { Invoke-Clean }
            '0' { Write-Host '  Bye.' -ForegroundColor Cyan; return }
            default { Write-Host "  Unknown choice: $choice" -ForegroundColor Yellow }
        }
        Write-Host ''
        Write-Host '------------------------------------------------------------'
        Write-Host ''
    }
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
Show-Banner
switch ($Action) {
    'menu'  { Invoke-Menu }
    'scan'  { Invoke-Scan;  exit $script:LastActionExitCode }
    'pick'  { Invoke-Pick;  exit $script:LastActionExitCode }
    'run'   { Invoke-Run;   exit $script:LastActionExitCode }
    'synth' { Invoke-Synth; exit $script:LastActionExitCode }
    'clean' { Invoke-Clean; exit $script:LastActionExitCode }
    'open'  { Invoke-Open;  exit $script:LastActionExitCode }
    'help'  { Show-Help; exit 0 }
}
