[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repositoryRoot 'docs\typora\opercerta-index.css'
$themeDirectory = Join-Path $env:APPDATA 'Typora\themes'
$target = Join-Path $themeDirectory 'opercerta-index.css'

if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Typora theme source is missing: $source"
}

New-Item -ItemType Directory -Path $themeDirectory -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Force

Write-Host "Installed Typora theme: $target"
Write-Host 'Restart Typora, then select Theme > OperCerta Index.'
