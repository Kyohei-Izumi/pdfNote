<#
.SYNOPSIS
  Fetches makeappx.exe / signtool.exe / makepri.exe into store\tools\.

.DESCRIPTION
  These live in the Windows SDK, but the same binaries ship in the NuGet
  package Microsoft.Windows.SDK.BuildTools (about 22 MB), so the whole SDK
  does not have to be installed just to pack an MSIX. Nothing is installed
  system-wide: the files land in store\tools\ and build_msix.ps1 finds them.
#>
[CmdletBinding()]
param([string]$Version = 'latest')

$ErrorActionPreference = 'Stop'
$store = Split-Path -Parent $MyInvocation.MyCommand.Path
$tools = Join-Path $store 'tools'
$url = if ($Version -eq 'latest') {
  'https://www.nuget.org/api/v2/package/Microsoft.Windows.SDK.BuildTools'
} else {
  "https://www.nuget.org/api/v2/package/Microsoft.Windows.SDK.BuildTools/$Version"
}

New-Item -ItemType Directory -Path $tools -Force | Out-Null
$package = Join-Path $tools 'sdk-buildtools.nupkg'
Invoke-WebRequest -Uri $url -OutFile $package -UseBasicParsing

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($package)
try {
  foreach ($entry in $archive.Entries) {
    if ($entry.FullName -notmatch '/x64/') { continue }
    # Folder entries have an empty Name.
    if (-not $entry.Name) { continue }
    # Everything under x64, not just the executables and libraries:
    # makeappx and signtool bind to appxpackaging.dll / mssign32.dll /
    # wintrust.dll through side-by-side assembly manifests
    # (Microsoft.Windows.Build.Appx.*.dll.manifest, signtool.exe.manifest,
    # wintrust.dll.ini, en-US\*.mui). Filtering those out left tools that
    # would not start at all: "The application has failed to start because
    # its side-by-side configuration is incorrect" (v5.26 review F3-03).

    $target = Join-Path $tools ($entry.FullName -replace '/', '\')
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    # A freshly written .exe can be held for a moment by an antivirus scan or
    # a sync client (OneDrive), and ExtractToFile then fails setting its date
    # ("used by another process"). Try again for a few seconds.
    for ($attempt = 1; ; $attempt++) {
      try {
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $true)
        break
      } catch {
        $problem = $_.Exception
        if ($problem -is [System.Management.Automation.MethodInvocationException]) {
          $problem = $problem.InnerException
        }
        if (-not ($problem -is [System.IO.IOException]) -or $attempt -ge 10) { throw }
        Start-Sleep -Milliseconds 500
      }
    }
  }
} finally {
  $archive.Dispose()
}
Remove-Item $package -Force

$makeappx = Get-ChildItem $tools -Recurse -Filter 'makeappx.exe' | Select-Object -First 1
if (-not $makeappx) { throw 'makeappx.exe was not extracted.' }
# Prove it actually runs: an incomplete extraction leaves a makeappx.exe
# that exists but cannot start, and that failure used to surface only
# later, inside build_msix.ps1, as an unexplained side-by-side error.
$banner = & $makeappx.FullName 2>&1 | Out-String
if ($banner -notmatch 'MakeAppx') {
  throw "makeappx.exe was extracted but does not start, so the extraction is incomplete:`n$banner"
}

"makeappx: $($makeappx.FullName)"
