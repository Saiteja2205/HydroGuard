# HydroGuard FastAPI backend

The backend is the authoritative store and API for nodes, sensor readings, alerts, forecasts, model errors, and adaptive weights. It uses FastAPI, Pydantic, SQLAlchemy, and SQLite. Android Room is a client-side cache/offline store, not a competing authority.

## Active data contract

The five product parameters are pH, TDS, turbidity, temperature, and experimental optical water colour. Readings preserve the TCS34725 raw `red`, `green`, `blue`, and `clear` counts and may carry `optical_colour_index` and a `calibration_id`. There is no validated index formula or calibration protocol yet; the field must not be interpreted as a contaminant measurement. Calibration records can retain sensor, timestamp, reference sample, and metadata.

Reading sources include `REAL_SENSOR`, `HISTORICAL_DATA`, and `SIMULATED_DEVELOPMENT`. Forecast inputs must use a single source. APIs reject legacy EC/DO/flow fields; legacy SQL columns remain only for database compatibility. Optical colour is not forecast and is excluded from the application-specific HydroGuard Water Quality Index.

## Forecasting and evaluation

The active forecast contract uses pH, TDS, turbidity, temperature, and optical_colour_index with LSTM, PatchTST, and TimeMixer. The request must contain complete, valid, timestamped observations in strictly increasing order, with no duplicates or future dates. At least 30 observations are required by default; configure this with `HYDROGUARD_FORECAST_MIN_HISTORY`. No generated history is used to satisfy the minimum.

Forecast records retain node, target and creation times, input interval, per-model and ensemble predictions, parameter-specific weights, source, model versions, and weight strategy. An actual reading is matched to target forecasts only for the same node and source. Errors are recorded per model and parameter; rolling MAE/RMSE drives persisted weights. In development, when comparable rolling errors are not yet available, the initial parameter-specific weights come from the 30-observation validation split and are explicitly disclosed; outside development, equal weights are disclosed until comparable error history exists.

The active versioned five-parameter checkpoints are trained with `ml/training/train_five_parameter_development.py` on exactly 200 `SIMULATED_DEVELOPMENT` observations. It uses chronological observation splits (140/30/30), 30-observation context windows, and training-only scaler fitting. Validation scores are used to calculate parameter-specific initial adaptive ensemble weights; these are development metrics only. Optical colour remains experimental and is not a validated safety measurement.

## Run locally

Use Python 3.10 or newer, create a virtual environment, install `requirements.txt`, then start the development server:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For this repository's Android development setup, run `.\scripts\run-development.ps1` from the backend folder. It loads the ignored project-root `.dev-auth.env`, enables the development-only demo identity bridge, and binds Uvicorn to the selected Wi-Fi or Ethernet IPv4 address on port 8000 so a physical phone on that LAN can connect. Never commit `.dev-auth.env`.

The development computer's active Wi-Fi IPv4 address was verified as `10.0.96.236`. The Android debug URL defaults to `http://10.0.96.236:8000/`; if DHCP changes that address, check the current Wi-Fi IPv4 address and rebuild with the replacement:

```powershell
$env:HYDROGUARD_API_BASE_URL = "http://<current-wifi-ipv4>:8000/"
.\gradlew.bat :app:assembleDebug
```

Open `http://10.0.96.236:8000/api/v1/health` from a device on the same network to check the API. The phone and development computer must share a network that allows local device traffic, and Windows Firewall must allow inbound TCP port 8000. If the existing `HydroGuard FastAPI 8000` rule allows remote addresses beyond the local subnet, run `Set-NetFirewallRule -DisplayName "HydroGuard FastAPI 8000" -RemoteAddress LocalSubnet` from an Administrator PowerShell window. The main/release Android network policy denies cleartext HTTP; the debug build alone permits the development HTTP URL. Release builds require a production HTTPS URL.

The debug Student/Admin demo buttons send the token from `.dev-auth.env` through the three `X-HydroGuard-Development-*` headers. They appear only in debug builds, and the backend accepts them only with `HYDROGUARD_ENVIRONMENT=development`, `HYDROGUARD_ENABLE_DEV_AUTH=true`, the matching token, and one of the two fixed demo identities. Google sign-in continues to use Firebase Authentication and a server-verified ID token.

## Authentication and hostel APIs

Google sign-in exchanges the Google credential through Firebase Authentication. Android then sends the Firebase ID token to `POST /api/v1/auth/bootstrap`. The backend verifies the token, UID, verified email, and configured Firebase project. New students are provisioned as `STUDENT` only when their verified email domain exactly matches `HYDROGUARD_ALLOWED_STUDENT_DOMAINS` (comma-separated). Existing users are resolved by Firebase UID and persistent HydroGuard account status. Firebase custom role claims are synchronized for Android token refresh; protected API requests authorize from the HydroGuard database record, never a client-supplied role or token role claim alone.

Configure the approved student domains on the backend, for example `HYDROGUARD_ALLOWED_STUDENT_DOMAINS=vrsec.ac.in,siddhartha.edu.in`. Set this to the institution's actual approved domains; an unset or unmatched domain does not auto-provision a student.

The Android debug-only Student and Admin demo buttons use the fixed identities `demo.student@hydroguard.local` and `demo.admin@hydroguard.local`. They send the local token from `.dev-auth.env` in the development authentication headers. The token is present in debug builds only and omitted from release builds; treat debug APKs as development artifacts and rotate the token if one is shared outside the team. The backend accepts the headers only when it is explicitly in development mode, the enable flag is true, and the token and role match one of those fixed identities. Google sign-in is a separate flow that uses a Firebase ID token verified by the backend.

There is no public admin registration. Bootstrap the first administrator from a trusted backend operator shell after that Google account exists in Firebase Authentication and has a verified email:

```powershell
$env:HYDROGUARD_FIREBASE_PROJECT_ID = "hydroguard-4a606"
python .\scripts\bootstrap_first_admin.py "first-admin@college.edu"
```

The command uses Application Default Credentials and creates the first persistent `ADMIN` account and custom role claim. It refuses to replace an existing first admin. Afterward, active admins can add faculty from the Android Admin Management section; each invite creates a pending backend record, and the faculty member must sign in with the invited verified email to activate it. The user table has no fixed admin count. Admins can activate, suspend, or revoke other admin records. The backend checks account status on every request and checks Firebase token revocation.

Sensor `POST /readings` requires `X-Sensor-Token` matching `HYDROGUARD_SENSOR_API_KEY`. Firebase and sensor authentication fail closed when unconfigured.

`/hostel/issues` supports student-owned issue creation/listing, admin status changes with a persisted timeline, student resolution feedback, and reopen requests. `/hostel/notices`, `/hostel/emergency-contacts`, `/hostel/lost-found`, and `/hostel/feedback` provide persisted hostel services. Administrative mutations and views are role-protected. Emergency contacts are empty until verified values are entered by an administrator. Image fields are HTTPS references only; no upload endpoint exists.

`GET /research/export.csv` requires an admin token and exports stored readings, forecast/model evaluations, calibration metadata, and alert annotations. Fields remain empty where no measurement or evaluation exists. It does not generate or infer missing research values.

## Test environment

Install `requirements.txt` plus `pytest` to run the backend and ML suite with `python -m pytest tests -q`. Syntax checks can be run with `python -m compileall -q app ml tests`.

## Limitations and provenance

Development fixtures and simulated records are not field measurements. `REAL_SENSOR` is provenance metadata, not proof of calibration or scientific validation. The TCS34725 requires controlled illumination, fixed geometry, and reference samples before an optical index can be defined. This backend makes no drinking-water safety certification or real-world model-accuracy claim.
