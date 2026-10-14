$ErrorActionPreference = 'Stop'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) {
    throw 'Visual Studio Build Tools were not found.'
}
$installation = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) {
    throw 'Visual Studio C++ build tools were not found.'
}
$msbuild = Join-Path $installation 'MSBuild\Current\Bin\MSBuild.exe'
& $msbuild (Join-Path $PSScriptRoot 'Mon3tr.vcxproj') '/p:Configuration=Release' '/p:Platform=x64' '/m' '/v:minimal'
if ($LASTEXITCODE -ne 0) {
    throw "MSBuild failed with exit code $LASTEXITCODE"
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'build\x64\Release\Mon3tr.exe') -Destination (Join-Path $PSScriptRoot 'Mon3tr.exe') -Force
Write-Output (Join-Path $PSScriptRoot 'Mon3tr.exe')
