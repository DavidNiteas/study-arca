param([Parameter(ValueFromRemainingArguments = $true)][string[]]$ProgramArgs)

$candidate = if ($env:SA_HOME) { [IO.Path]::GetFullPath($env:SA_HOME) } else { $PSScriptRoot }
while ($candidate -and -not (Test-Path (Join-Path $candidate 'scripts/sa.py'))) {
    $parent = Split-Path -Parent $candidate
    if ($parent -eq $candidate) { $candidate = $null } else { $candidate = $parent }
}
if (-not $candidate) {
    throw "找不到 Study Arca scripts/sa.py；请设置 SA_HOME"
}

& python (Join-Path $candidate 'scripts/sa.py') program @ProgramArgs
exit $LASTEXITCODE
