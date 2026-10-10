$ErrorActionPreference = 'Stop'

$backendRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $backendRoot
$authSettingsPath = Join-Path $repositoryRoot '.dev-auth.env'
if (-not (Test-Path -LiteralPath $authSettingsPath -PathType Leaf)) {
    throw "Missing ignored development settings file: $authSettingsPath"
}

# Windows PowerShell 5.1 writes a UTF-8 BOM; strip it or the first key is unreadable.
$authRaw = Get-Content -LiteralPath $authSettingsPath -Raw
if ($authRaw.Length -gt 0 -and $authRaw[0] -eq [char]0xFEFF) { $authRaw = $authRaw.Substring(1) }
$authSettings = $authRaw | ConvertFrom-StringData
if ($authSettings.HYDROGUARD_ENVIRONMENT -notin @('development', 'dev')) {
    throw 'The backend development script requires HYDROGUARD_ENVIRONMENT=development.'
}
if ($authSettings.HYDROGUARD_ENABLE_DEV_AUTH -ne 'true' -or [string]::IsNullOrWhiteSpace($authSettings.HYDROGUARD_DEV_API_TOKEN)) {
    throw 'The development identity bridge needs an explicit enable flag and non-empty token.'
}

$env:HYDROGUARD_ENVIRONMENT = 'development'
$env:HYDROGUARD_ENABLE_DEV_AUTH = 'true'
$env:HYDROGUARD_DEV_API_TOKEN = $authSettings.HYDROGUARD_DEV_API_TOKEN
if ([string]::IsNullOrWhiteSpace($env:HYDROGUARD_FIREBASE_PROJECT_ID)) {
    $env:HYDROGUARD_FIREBASE_PROJECT_ID = 'hydroguard-4a606'
}

$upInterfaces = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
    Where-Object { $_.OperationalStatus -eq 'Up' -and $_.NetworkInterfaceType -ne 'Loopback' }
$interfacesWithGateway = $upInterfaces | Where-Object {
    @($_.GetIPProperties().GatewayAddresses | Where-Object {
        $_.Address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
        -not $_.Address.IsLoopback
    }).Count -gt 0
}
$networkInterface = $interfacesWithGateway |
    Where-Object { $_.NetworkInterfaceType -eq [System.Net.NetworkInformation.NetworkInterfaceType]::Wireless80211 } |
    Select-Object -First 1
if (-not $networkInterface) {
    $networkInterface = $interfacesWithGateway |
        Where-Object { $_.NetworkInterfaceType -eq [System.Net.NetworkInformation.NetworkInterfaceType]::Ethernet } |
        Select-Object -First 1
}
if (-not $networkInterface) {
    $networkInterface = $interfacesWithGateway | Select-Object -First 1
}
$lanAddress = $networkInterface.GetIPProperties().UnicastAddresses |
    Where-Object {
        $_.Address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
        -not $_.Address.IsLoopback -and
        -not $_.Address.ToString().StartsWith('169.254.')
    } |
    Select-Object -First 1 |
    ForEach-Object { $_.Address.ToString() }

if ([string]::IsNullOrWhiteSpace($lanAddress)) {
    throw 'No active Wi-Fi or Ethernet IPv4 address with a gateway was found. Connect the development computer to the same network as the phone.'
}

# Persist the detected address so Android debug builds target it automatically
# (app/build.gradle.kts reads HYDROGUARD_API_BASE_URL from .dev-auth.env).
# Emulators on this computer can instead use http://10.0.2.2:8000/.
$appBaseUrl = "http://${lanAddress}:8000/"
$envLines = @($authRaw -split "\r?\n" |
    Where-Object { $_ -notmatch '^\s*HYDROGUARD_API_BASE_URL\s*=' -and $_ -match '\S' }) +
    @("HYDROGUARD_API_BASE_URL=$appBaseUrl")
[System.IO.File]::WriteAllLines($authSettingsPath, $envLines, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Detected LAN IPv4 $lanAddress on '$($networkInterface.Name)'."
Write-Host "Android debug builds will use API base URL: $appBaseUrl (emulator alternative: http://10.0.2.2:8000/)"
Write-Host 'Rebuild the debug APK after this script runs, then install it on the phone.'
Write-Host 'If the phone cannot connect, allow inbound TCP 8000 for python in Windows Defender Firewall.'
Write-Host 'Starting HydroGuard on 0.0.0.0:8000 so phones on the LAN can reach it.'
Write-Host 'Keep this terminal open while the Android phone uses the API.'

# Uvicorn binds 0.0.0.0 (all interfaces); $lanAddress above is only used for the client URL.
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { $python = 'python' }

Push-Location $backendRoot
try {
    & $python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
}
finally {
    Pop-Location
}
