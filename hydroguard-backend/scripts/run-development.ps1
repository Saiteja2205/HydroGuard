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

# Optional backend settings carried by the same file. These used to be parsed
# into $authSettings and then silently dropped, so the backend read an empty
# student-domain allowlist and rejected every registration with HTTP 403
# ("College email domain not approved. Approved domains are: .") even though
# .dev-auth.env had configured the domains. A missing allowlist is now loud
# instead of silently disabling Create Account and college-domain sign-in.
$allowedStudentDomains = $authSettings.HYDROGUARD_ALLOWED_STUDENT_DOMAINS
if (-not [string]::IsNullOrWhiteSpace($allowedStudentDomains)) {
    $env:HYDROGUARD_ALLOWED_STUDENT_DOMAINS = $allowedStudentDomains
} else {
    Write-Warning 'HYDROGUARD_ALLOWED_STUDENT_DOMAINS is empty in .dev-auth.env. Student registration and college-domain sign-in will be rejected until it is set (comma-separated, e.g. vrsec.ac.in,siddhartha.edu.in).'
}
if ([string]::IsNullOrWhiteSpace($env:HYDROGUARD_FIREBASE_PROJECT_ID)) {
    $env:HYDROGUARD_FIREBASE_PROJECT_ID = 'hydroguard-4a606'
}
if (-not [string]::IsNullOrWhiteSpace($authSettings.HYDROGUARD_THINGSPEAK_CHANNEL_ID)) {
    $env:HYDROGUARD_THINGSPEAK_CHANNEL_ID = $authSettings.HYDROGUARD_THINGSPEAK_CHANNEL_ID
}
if (-not [string]::IsNullOrWhiteSpace($authSettings.HYDROGUARD_THINGSPEAK_READ_API_KEY)) {
    $env:HYDROGUARD_THINGSPEAK_READ_API_KEY = $authSettings.HYDROGUARD_THINGSPEAK_READ_API_KEY
}

# Firebase Admin resolves its service-account key lazily, so a missing key used
# to let the backend start normally and only fail later with an opaque HTTP 503
# on the first sign-in. Resolve it here and stop with a clear message instead.
if ([string]::IsNullOrWhiteSpace($env:GOOGLE_APPLICATION_CREDENTIALS)) {
    $credentialCandidates = @(
        (Join-Path $env:USERPROFILE '.firebase\hydroguard-admin.json'),
        (Join-Path $backendRoot 'firebase-service-account.json'),
        (Join-Path $backendRoot 'serviceAccountKey.json')
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    if ($credentialCandidates.Count -gt 0) {
        $env:GOOGLE_APPLICATION_CREDENTIALS = $credentialCandidates[0]
    }
}
if ([string]::IsNullOrWhiteSpace($env:GOOGLE_APPLICATION_CREDENTIALS) -or
    -not (Test-Path -LiteralPath $env:GOOGLE_APPLICATION_CREDENTIALS -PathType Leaf)) {
    throw 'GOOGLE_APPLICATION_CREDENTIALS does not point at a Firebase service-account key file. Registration, login and account bootstrap all return HTTP 503 without it. Set GOOGLE_APPLICATION_CREDENTIALS to the key file and re-run this script.'
}
Write-Host "Using Firebase service-account key: $env:GOOGLE_APPLICATION_CREDENTIALS"
Write-Host 'No password, token or key material is ever written to the log.'

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
