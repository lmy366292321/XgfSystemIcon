[CmdletBinding()]
param(
    [ValidateSet('doctor', 'check-icon', 'check-batch', 'qa-sheet', 'relation-sheet', 'workflow', 'color-record', 'composition-plan', 'composition-case', 'test')]
    [string]$Operation = 'doctor',
    [string[]]$Arguments = @(),
    [string]$TestRoot
)

$ErrorActionPreference = 'Stop'
$skillRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$configFile = Join-Path $skillRoot 'runtime.local.json'
try {
    if (-not (Test-Path -LiteralPath $configFile -PathType Leaf)) {
        throw 'Missing runtime.local.json: configure an existing Python with Pillow; no automatic installation.'
    }
    $config = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json
    if ($config.schema_version -ne 1) { throw 'Unsupported runtime config schema.' }
    $pythonExe = [string]$config.python_executable
    if (-not [System.IO.Path]::IsPathRooted($pythonExe) -or
        -not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        throw 'Configured Python is missing; inspect runtime.local.json. No PATH fallback.'
    }
    $actualHash = (Get-FileHash -LiteralPath $pythonExe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $config.python_executable_sha256) {
        throw 'Configured Python executable changed. Re-verify it before updating the local configuration.'
    }
    $probe = & $pythonExe -X utf8 -B -c 'import json,sys,PIL; print(json.dumps({"python":sys.executable,"python_version":".".join(map(str,sys.version_info[:3])),"pillow_version":PIL.__version__}))'
    if ($LASTEXITCODE -ne 0) { throw 'Configured Python cannot import Pillow.' }
    $runtime = $probe | ConvertFrom-Json
    if ($runtime.python_version -ne $config.python_version -or
        $runtime.pillow_version -ne $config.pillow_version) {
        throw 'Python/Pillow version changed. Re-verify the runtime; no automatic installation or fallback.'
    }
    if ($Operation -eq 'doctor') {
        [pscustomobject]@{
            status = 'pass'
            skill_root = $skillRoot
            release = $config.local_release
            python = $runtime.python
            python_version = $runtime.python_version
            pillow_version = $runtime.pillow_version
            executable_sha256 = $actualHash
        } | ConvertTo-Json
        exit 0
    }
    if ($Operation -eq 'test') {
        if (-not $TestRoot) { throw 'test requires -TestRoot pointing to a writable project fixture directory.' }
        $fixtureRoot = [System.IO.Path]::GetFullPath($TestRoot)
        if ($fixtureRoot -eq $skillRoot -or
            $fixtureRoot.StartsWith($skillRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Test fixtures must be outside the installed skill.'
        }
        $priorTestRoot = $env:XGF_TEST_ROOT
        try {
            $env:XGF_TEST_ROOT = $fixtureRoot
            & $pythonExe -X utf8 -B -m unittest discover -s $PSScriptRoot -p 'test_*.py' -v
            $result = $LASTEXITCODE
        } finally {
            $env:XGF_TEST_ROOT = $priorTestRoot
        }
    } else {
        $scripts = @{
            'check-icon' = 'check_icon.py'
            'check-batch' = 'check_batch.py'
            'qa-sheet' = 'build_qa_sheet.py'
            'relation-sheet' = 'build_relation_sheet.py'
            'workflow' = 'review_workflow.py'
            'color-record' = 'color_record.py'
            'composition-plan' = 'composition_preflight.py'
            'composition-case' = 'replay_composition_case.py'
        }
        & $pythonExe -X utf8 -B (Join-Path $PSScriptRoot $scripts[$Operation]) @Arguments
        $result = $LASTEXITCODE
    }
    exit $result
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 2
}
