# HydroGuard FastAPI backend

The backend is the authoritative store and API for nodes, sensor readings, alerts, forecasts, model errors, and adaptive weights. It uses FastAPI, Pydantic, SQLAlchemy, and SQLite. Android Room is a client-side cache/offline store, not a competing authority.

## Active data contract

The five product parameters are pH, TDS, turbidity, temperature, and experimental optical water colour. Readings preserve the TCS34725 raw `red`, `green`, `blue`, and `clear` counts and may carry `optical_colour_index` and a `calibration_id`. There is no validated index formula or calibration protocol yet; the field must not be interpreted as a contaminant measurement. Calibration records can retain sensor, timestamp, reference sample, and metadata.

Reading sources are `REAL_SENSOR`, `HISTORICAL_DATA`, `DEMO`, and `SIMULATED`. Forecast inputs must use a single source. APIs reject legacy EC/DO/flow fields; legacy SQL columns remain only for database compatibility. Optical colour is not forecast and is excluded from the application-specific HydroGuard Water Quality Index.

## Forecasting and evaluation

The active forecast contract uses pH, TDS, turbidity, temperature, and optical_colour_index with LSTM, PatchTST, and TimeMixer. The request must contain complete, valid, timestamped observations in strictly increasing order, with no duplicates or future dates. At least 30 observations are required by default; configure this with `HYDROGUARD_FORECAST_MIN_HISTORY`. No generated history is used to satisfy the minimum.

Forecast records retain node, target and creation times, input interval, per-model and ensemble predictions, parameter-specific weights, source, model versions, and weight strategy. An actual reading is matched to target forecasts only for the same node and source. Errors are recorded per model and parameter; rolling MAE/RMSE drives persisted weights. Equal weights are disclosed as the initial strategy until comparable error history exists.

The active versioned five-parameter checkpoints are trained with `ml/training/train_five_parameter_development.py` on exactly 200 simulated development observations. It uses chronological observation splits (140/30/30), 30-day context windows, and training-only scaler fitting. Validation scores are used to calculate parameter-specific initial adaptive ensemble weights; these are development metrics only. Optical colour remains experimental and is not a validated safety measurement.

## Run locally

Use Python 3.10 or newer, create a virtual environment, install `requirements.txt`, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs are available at `http://127.0.0.1:8000/docs`; health is at `/api/v1/health`.

### Android debug connection

The Android debug build defaults to `http://10.0.2.2:8000/`, the Android Emulator's host bridge. Keep the backend running on port 8000 while using the app. For the local Student Demo and Administrator Demo buttons to access authenticated hostel endpoints, enable the explicitly development-only identity bridge and configure the same random token in both processes. This bridge is disabled by default, accepts only the two local demo identities, and is not enabled in release builds. The Android build reads `HYDROGUARD_DEV_API_TOKEN` from a Gradle property or environment variable, or from the ignored project-root `.dev-auth.env` file. Never commit that file.

In the backend PowerShell terminal, load the same ignored project-root `.dev-auth.env` file:

```powershell
$devAuthSettings = Get-Content ..\.dev-auth.env -Raw | ConvertFrom-StringData
$env:HYDROGUARD_ENVIRONMENT = $devAuthSettings.HYDROGUARD_ENVIRONMENT
$env:HYDROGUARD_ENABLE_DEV_AUTH = $devAuthSettings.HYDROGUARD_ENABLE_DEV_AUTH
$env:HYDROGUARD_DEV_API_TOKEN = $devAuthSettings.HYDROGUARD_DEV_API_TOKEN
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In the Android project PowerShell terminal, Gradle reads that file automatically. You can also provide the token using the existing environment-variable or Gradle-property mechanism:

```powershell
$env:HYDROGUARD_API_BASE_URL = "http://10.0.2.2:8000/"
.\gradlew.bat :app:assembleDebug
```

The debug network policy permits cleartext only to the Android Emulator bridge (`10.0.2.2`) and the configured development laptop address (`10.79.232.152`). The shared/release policy denies cleartext HTTP. For an Android Emulator, keep the default base URL and loopback backend bind shown above. For a physical device, bind FastAPI to the LAN interface and build the debug app with the laptop URL:

```powershell
# Backend terminal (physical-device access)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Android project terminal
$env:HYDROGUARD_API_BASE_URL = "http://10.79.232.152:8000/"
.\gradlew.bat :app:assembleDebug
```

The phone and laptop must be on a network that allows device-to-device traffic, and the host firewall must allow port 8000. This setting does not alter the release URL or its HTTPS requirement.

## Authentication and hostel APIs

Protected endpoints accept Firebase ID tokens as `Authorization: Bearer <token>`. Set `HYDROGUARD_FIREBASE_PROJECT_ID` and configure Google Application Default Credentials. A token without a role custom claim is treated as a student; admin endpoints require the server-managed Firebase custom claim `role=ADMIN`. Do not grant admin claims from client code. Sensor `POST /readings` requires `X-Sensor-Token` matching `HYDROGUARD_SENSOR_API_KEY`. These integrations are fail-closed when unconfigured.

`/hostel/issues` supports student-owned issue creation/listing, admin status changes with a persisted timeline, student resolution feedback, and reopen requests. `/hostel/notices`, `/hostel/emergency-contacts`, `/hostel/events`, `/hostel/lost-found`, and `/hostel/feedback` provide persisted hostel services. Administrative mutations and views are role-protected. Emergency contacts are empty until verified values are entered by an administrator. Image fields are HTTPS references only; no upload endpoint exists.

`GET /research/export.csv` requires an admin token and exports stored readings, forecast/model evaluations, calibration metadata, and alert annotations. Fields remain empty where no measurement or evaluation exists. It does not generate or infer missing research values.

## Test environment

Install `requirements.txt` plus `pytest` to run the backend and ML suite with `python -m pytest tests -q`. Syntax checks can be run with `python -m compileall -q app ml tests`.

## Limitations and provenance

Development fixtures and simulated records are not field measurements. `REAL_SENSOR` is provenance metadata, not proof of calibration or scientific validation. The TCS34725 requires controlled illumination, fixed geometry, and reference samples before an optical index can be defined. This backend makes no drinking-water safety certification or real-world model-accuracy claim.
