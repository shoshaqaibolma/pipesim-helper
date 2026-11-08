# Prints the path of the PIPESIM Python Toolkit's python.exe (the Python that can import sixgill).
# Used by install.bat. Looks at earlier settings, then typical install folders on every drive, then asks.
$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot

function Test-Py($p) {
    if (-not $p -or -not (Test-Path -LiteralPath $p)) { return $false }
    & $p -c "import sixgill" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

$cands = New-Object System.Collections.Generic.List[string]

# 1. what an earlier installation used
$st = Join-Path $root 'settings.toml'
if (Test-Path $st) {
    $m = Select-String -LiteralPath $st -Pattern "^pipesim_python\s*=\s*'(.*)'"
    if ($m) { $cands.Add($m.Matches[0].Groups[1].Value) }
}
$cfg = Join-Path $root 'config.bat'
if (Test-Path $cfg) {
    $m = Select-String -LiteralPath $cfg -Pattern '^\s*set\s+PIPESIM_PY=(.*)$'
    if ($m) { $cands.Add($m.Matches[0].Groups[1].Value.Trim('"', ' ')) }
}

# 2. typical install folders (Program Files\Schlumberger\..., D:\Program\Pipesim toolkit\..., ...) on every drive
$drives = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null } | ForEach-Object { $_.Root }
foreach ($d in $drives) {
    $tops = Get-ChildItem -LiteralPath $d -Directory -Force | Where-Object { $_.Name -match 'program|schlumberger|slb|pipesim' }
    foreach ($top in $tops) {
        Get-ChildItem -LiteralPath $top.FullName -Filter python.exe -Recurse -Depth 3 -File |
            Where-Object { $_.FullName -match 'pipesim|schlumberger|slb' } |
            ForEach-Object { $cands.Add($_.FullName) }
    }
}
foreach ($c in ($cands | Select-Object -Unique)) {
    if (Test-Py $c) { Write-Output $c; exit 0 }
}

# 3. not found: let the user pick it
Add-Type -AssemblyName System.Windows.Forms
[void][System.Windows.Forms.MessageBox]::Show(
    "The PIPESIM Python Toolkit was not found automatically.`n`nIn the next window, open the folder where the PIPESIM Python Toolkit is installed and select its python.exe.",
    "PIPESIM Assistant setup")
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Filter = 'python.exe|python.exe'
$dlg.Title = 'Select the python.exe of the PIPESIM Python Toolkit'
if ($dlg.ShowDialog() -eq 'OK') {
    if (Test-Py $dlg.FileName) { Write-Output $dlg.FileName; exit 0 }
    [void][System.Windows.Forms.MessageBox]::Show(
        "This python.exe cannot load the PIPESIM Python Toolkit (sixgill). Pick the one inside the toolkit's folder.",
        "PIPESIM Assistant setup")
}
exit 1
