$ErrorActionPreference = 'Stop'

$backendRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $backendRoot
$authSettingsPath = Join-Path $repositoryRoot '.dev-auth.env'
if (-not (Test-Path -LiteralPath $authSettingsPath -PathType Leaf)) {
    throw "Missing ignored development settings file: $authSettingsPath"
}

$authSettings = Get-Content -LiteralPath $authSettingsPath -Raw | ConvertFrom-StringData
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
Write-Host "Starting HydroGuard on $($lanAddress):8000. The API will accept connections through this LAN interface only."
Write-Host 'Keep this terminal open while the Android phone uses the API.'

Push-Location $backendRoot
try {
    python -m uvicorn app.main:app --host $lanAddress --port 8000
}
finally {
    Pop-Location
}
