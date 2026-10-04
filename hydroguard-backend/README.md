# HydroGuard FastAPI backend

The backend is the authoritative store and API for nodes, sensor readings, alerts, forecasts, model errors, and adaptive weights. It uses FastAPI, Pydantic, SQLAlchemy, and SQLite. Android Room is a client-side cache/offline store, not a competing authority.

## Active data contract

The five product parameters are pH, TDS, turbidity, temperature, and experimental optical water colour. Readings preserve the TCS34725 raw `red`, `green`, `blue`, and `clear` counts and may carry `optical_colour_index` and a `calibration_id`. There is no validated index formula or calibration protocol yet; the field must not be interpreted as a contaminant measurement. Calibration records can retain sensor, timestamp, reference sample, and metadata.

Reading sources are `REAL_SENSOR`, `HISTORICAL_DATA`, `DEMO`, and `SIMULATED`. Forecast inputs must use a single source. APIs reject legacy EC/DO/flow fields; legacy SQL columns remain only for database compatibility. Optical colour is not forecast and is excluded from the application-specific HydroGuard Water Quality Index.

## Forecasting and evaluation

Forecasting uses LSTM, PatchTST, and TimeMixer checkpoints for pH, TDS, turbidity, and temperature. Existing checkpoints and metrics originate from synthetic four-parameter data and are not field accuracy claims. The request must contain complete, valid, timestamped observations in strictly increasing order, with no duplicates or future dates. At least 30 observations are required by default; configure this with `HYDROGUARD_FORECAST_MIN_HISTORY`. No generated history is used to satisfy the minimum.

Forecast records retain node, target and creation times, input interval, per-model and ensemble predictions, parameter-specific weights, source, model versions, and weight strategy. An actual reading is matched to target forecasts only for the same node and source. Errors are recorded per model and parameter; rolling MAE/RMSE drives persisted weights. Equal weights are disclosed as the initial strategy until comparable error history exists.

Training uses chronological train/validation/test partitions and fits data scalers on training data. Optical-colour forecasting is unavailable pending validated observations and a suitable model.

## Run locally

Use Python 3.10 or newer, create a virtual environment, install `requirements.txt`, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs are available at `http://127.0.0.1:8000/docs`; health is at `/api/v1/health`.

## Authentication and hostel APIs

Protected endpoints accept Firebase ID tokens as `Authorization: Bearer <token>`. Set `HYDROGUARD_FIREBASE_PROJECT_ID` and configure Google Application Default Credentials. A token without a role custom claim is treated as a student; admin endpoints require the server-managed Firebase custom claim `role=ADMIN`. Do not grant admin claims from client code. Sensor `POST /readings` requires `X-Sensor-Token` matching `HYDROGUARD_SENSOR_API_KEY`. These integrations are fail-closed when unconfigured.

`/hostel/issues` supports student-owned issue creation/listing, admin status changes with a persisted timeline, student resolution feedback, and reopen requests. `/hostel/notices`, `/hostel/emergency-contacts`, `/hostel/events`, `/hostel/lost-found`, and `/hostel/feedback` provide persisted hostel services. Administrative mutations and views are role-protected. Emergency contacts are empty until verified values are entered by an administrator. Image fields are HTTPS references only; no upload endpoint exists.

`GET /research/export.csv` requires an admin token and exports stored readings, forecast/model evaluations, calibration metadata, and alert annotations. Fields remain empty where no measurement or evaluation exists. It does not generate or infer missing research values.

## Test environment

Install `requirements.txt` plus `pytest` to run the backend and ML suite with `python -m pytest tests -q`. Syntax checks can be run with `python -m compileall -q app ml tests`.

## Limitations and provenance

Development fixtures and simulated records are not field measurements. `REAL_SENSOR` is provenance metadata, not proof of calibration or scientific validation. The TCS34725 requires controlled illumination, fixed geometry, and reference samples before an optical index can be defined. This backend makes no drinking-water safety certification or real-world model-accuracy claim.
