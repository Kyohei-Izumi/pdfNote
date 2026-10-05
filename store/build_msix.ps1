<#
.SYNOPSIS
  Packs dist\pdfNote.exe into an MSIX for the Microsoft Store.

.DESCRIPTION
  Fills store\AppxManifest.template.xml with the values in store\identity.json,
  lays the package out under store\layout\, indexes its images with
  makepri.exe and runs makeappx.exe.

  The Store signs what it publishes, so an unsigned package is what you upload
  (Microsoft Learn, "App package requirements for MSIX app"). -Sign makes a
  self-signed test package instead, for installing on this PC; its certificate
  must be trusted first, which needs an administrator.

.PARAMETER MakeAppx
  Path to makeappx.exe. Without it the script looks in the Windows SDK, then
  in store\tools\ (where get_packaging_tools.ps1 puts the NuGet copy).

.PARAMETER MakePri
  Path to makepri.exe, looked for the same way.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File store\build_msix.ps1
#>
[CmdletBinding()]
param(
  [string]$MakeAppx,
  [string]$MakePri,
  [string]$SignTool,
  [switch]$Sign,
  [string]$CertificateThumbprint,
  # Another identity.json, e.g. test values for a package that is only
  # installed on this PC. The default is store\identity.json.
  [string]$Identity
)

$ErrorActionPreference = 'Stop'
$store = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $store
$exe = Join-Path $root 'dist\pdfNote.exe'
$layout = Join-Path $store 'layout'
$output = Join-Path $store 'out'

if (-not (Test-Path $exe)) {
  throw "dist\pdfNote.exe was not found. Run python -m PyInstaller pdfNote.spec --noconfirm first."
}

# --- the values from Partner Center -----------------------------------------
if (-not $Identity) { $Identity = Join-Path $store 'identity.json' }
# Not $identity: PowerShell variable names ignore case, so that name is the
# [string]$Identity parameter, and assigning the parsed object to it turns the
# object back into a string ("@{identity_name=...}"), whose properties are all
# empty.
$values = Get-Content $Identity -Raw -Encoding UTF8 | ConvertFrom-Json
$fields = @{
  '{{IDENTITY_NAME}}'          = $values.identity_name
  '{{IDENTITY_PUBLISHER}}'     = $values.identity_publisher
  '{{PUBLISHER_DISPLAY_NAME}}' = $values.publisher_display_name
  '{{RESERVED_NAME}}'          = $values.reserved_name
  '{{SHORT_DESCRIPTION}}'      = $values.short_description
}
foreach ($key in $fields.Keys) {
  if (-not $fields[$key] -or $fields[$key] -like 'REPLACE-WITH-*') {
    throw "store\identity.json has no value for $key. Copy it from Product identity in Partner Center."
  }
}

# --- the version, taken from the app so the two can never disagree ----------
$appVersion = (Select-String -Path (Join-Path $root 'app.py') -Pattern '^APP_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"').Matches[0].Groups[1].Value
$parts = $appVersion.Split('.')
# The Store requires the fourth part to be 0.
$packageVersion = '{0}.{1}.{2}.0' -f $parts[0], $parts[1], $parts[2]
$fields['{{VERSION}}'] = $packageVersion

$manifest = Get-Content (Join-Path $store 'AppxManifest.template.xml') -Raw -Encoding UTF8
foreach ($key in $fields.Keys) { $manifest = $manifest.Replace($key, $fields[$key]) }

# --- lay the package out -----------------------------------------------------
if (Test-Path $layout) { Remove-Item $layout -Recurse -Force }
New-Item -ItemType Directory -Path $layout | Out-Null
New-Item -ItemType Directory -Path (Join-Path $layout 'Assets') | Out-Null
Copy-Item $exe (Join-Path $layout 'pdfNote.exe')
Copy-Item (Join-Path $store 'Assets\*.png') (Join-Path $layout 'Assets')
# The licence and the usage notes travel with the app: the Store listing links
# to the AGPL text, and the app's own dialog reads legal\ from beside the exe.
Copy-Item (Join-Path $root 'LICENSE') (Join-Path $layout 'LICENSE')
Copy-Item (Join-Path $root 'LICENSE_NOTICE.txt') (Join-Path $layout 'LICENSE_NOTICE.txt')
if (Test-Path (Join-Path $root 'legal')) {
  Copy-Item (Join-Path $root 'legal') (Join-Path $layout 'legal') -Recurse
}
[System.IO.File]::WriteAllText((Join-Path $layout 'AppxManifest.xml'), $manifest, (New-Object System.Text.UTF8Encoding($false)))

# --- the SDK tools -----------------------------------------------------------
function Find-PackagingTool([string]$Name) {
  $candidates = @()
  $sdk = 'C:\Program Files (x86)\Windows Kits\10\bin'
  if (Test-Path $sdk) {
    $candidates += Get-ChildItem $sdk -Recurse -Filter $Name -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match '\\x64\\' } | Sort-Object FullName -Descending |
      Select-Object -ExpandProperty FullName
  }
  $candidates += Get-ChildItem (Join-Path $store 'tools') -Recurse -Filter $Name -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName
  $found = $candidates | Select-Object -First 1
  if (-not $found) {
    throw "$Name was not found. Run store\get_packaging_tools.ps1, or give its path as a parameter."
  }
  $found
}
if (-not $MakeAppx) { $MakeAppx = Find-PackagingTool 'makeappx.exe' }
if (-not $MakePri) { $MakePri = Find-PackagingTool 'makepri.exe' }
if (-not (Test-Path $output)) { New-Item -ItemType Directory -Path $output | Out-Null }

# --- resources.pri -----------------------------------------------------------
# Assets\ holds each image at several scales and target sizes, with the
# unplated variants for the taskbar and Start. Windows finds those only
# through the package's resource index: without resources.pri it takes the
# file name the manifest gives, which has no file of its own, and a package
# that did have one would show that single image, scaled, on a plate
# (Microsoft Learn, "Generating MSIX package components").
$priConfig = Join-Path $output 'priconfig.xml'
# The default language is the manifest's first, Japanese ("ja": one tag a
# language, 6.4).
& $MakePri createconfig /cf $priConfig /dq ja /o | Out-Null
if ($LASTEXITCODE -ne 0) { throw "makepri createconfig failed ($LASTEXITCODE)" }
# The default configuration splits the index by scale and language
# (resources.scale-200.pri, ...) for the resource packages of a bundle.
# This is a single package, and Windows reads only resources.pri from it:
# split, the 125-400% images would be left out of the index it reads.
$config = New-Object System.Xml.XmlDocument
$config.Load($priConfig)
$splitting = $config.SelectSingleNode('/resources/packaging')
if ($splitting) { [void]$config.DocumentElement.RemoveChild($splitting) }
$config.Save($priConfig)
& $MakePri new /pr $layout /cf $priConfig /mn (Join-Path $layout 'AppxManifest.xml') /of (Join-Path $layout 'resources.pri') /o
if ($LASTEXITCODE -ne 0) { throw "makepri new failed ($LASTEXITCODE)" }

# --- makeappx ----------------------------------------------------------------
$package = Join-Path $output ("pdfNote_{0}_x64.msix" -f $packageVersion)
if (Test-Path $package) { Remove-Item $package -Force }
& $MakeAppx pack /d $layout /p $package /o
if ($LASTEXITCODE -ne 0) { throw "makeappx pack failed ($LASTEXITCODE)" }

if ($Sign) {
  if (-not $CertificateThumbprint) {
    throw "-Sign needs -CertificateThumbprint: the thumbprint of a code-signing certificate whose subject is the Publisher in store\identity.json."
  }
  if (-not $SignTool) {
    $SignTool = (Get-ChildItem (Join-Path $store 'tools') -Recurse -Filter 'signtool.exe' -ErrorAction SilentlyContinue |
      Select-Object -First 1 -ExpandProperty FullName)
  }
  if (-not $SignTool) { throw "signtool.exe was not found." }
  & $SignTool sign /fd SHA256 /sha1 $CertificateThumbprint /t http://timestamp.digicert.com $package
  if ($LASTEXITCODE -ne 0) { throw "signtool sign failed ($LASTEXITCODE)" }
}

'{0} ({1:N1} MB)' -f $package, ((Get-Item $package).Length / 1MB)
