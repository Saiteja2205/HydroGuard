# HydroGuard

HydroGuard is a research prototype for water monitoring and forecasting. The repository contains an Android Kotlin/Jetpack Compose app, a FastAPI backend backed by SQLite, ML forecasting code, and an ESP32 sensor prototype.

## Active monitoring contract

The product contract contains five parameters: pH, TDS, turbidity, temperature, and an experimental optical water-colour index. The TCS34725's raw red, green, blue, and clear counts are retained independently of the optional index. No validated index formula or calibration protocol is currently established, so the index is not a contamination measurement. It does not identify any chemical or microbial contaminant.

EC, dissolved oxygen, and flow remain only in legacy storage or migration compatibility paths where needed. They are excluded from active reading and forecast APIs and the monitoring UI. The HydroGuard Water Quality Index is application-specific; it is not a drinking-water standard or a water-safety certification. Optical colour is excluded from its calculation.

## Data ownership and provenance

- **Backend authoritative:** sensor readings, nodes, alerts, forecasts, model errors, and persisted ensemble weights.
- **Android Room:** local cache and offline/demo state. It is not an independent authority for server readings or forecasts.
- **DEMO / SIMULATED:** development fixtures and simulated app readings. They must remain labelled and are not field observations.
- **HISTORICAL_DATA:** imported observations whose provenance is supplied by the data provider.
- **REAL_SENSOR:** sensor-originated readings. This label alone does not establish calibration or scientific validation.

The forecast API requires timestamped, complete pH/TDS/turbidity/temperature observations from one provenance source, in strict chronological order, and at least 30 records by default. The threshold is configurable with `HYDROGUARD_FORECAST_MIN_HISTORY`. Forecasts are never backfilled with generated observations. Optical-colour forecasts remain unavailable until suitable validated data and a model exist.

## Forecasting status

The ML code retains LSTM, PatchTST, and TimeMixer. Existing checkpoints and reported metrics were developed from synthetic four-parameter data (pH, TDS, turbidity, temperature); they are development artifacts, not real-world accuracy results. Forecast records preserve input interval, source, model versions, predictions, weights, and initial/adaptive strategy. Later actual readings are matched by node, target day, and source to record parameter- and model-specific errors and update persisted weights. Equal weights are an explicitly reported initial fallback until comparable performance history exists.

Training and validation must use chronological splits, with preprocessing fitted on training data only. No field-validation claim is made by this repository.

## Components

- **Android:** Kotlin, Jetpack Compose, Room cache, Retrofit/Moshi API client.
- **Backend:** Python FastAPI, Pydantic schemas, SQLAlchemy, SQLite.
- **Models:** LSTM, PatchTST, TimeMixer, plus a parameter-specific adaptive ensemble.
- **Sensor prototype:** ESP32 with water-quality sensors and TCS34725 optical colour sensor. Hardware integration and calibration remain experimental.

## Hostel platform and access control

The student app has HOME, WATER, REPORT, MY ISSUES, and PROFILE destinations. The API persists issue reports and timelines, resolution feedback and reopen requests, notices, verified emergency contacts, events, moderated Lost & Found submissions, and general hostel feedback in SQLite. The admin app has WATER and HOSTEL OPS sections; the latter reads these records from the backend and provides issue workflow, notice creation/deletion, contact creation/deactivation, and Lost & Found moderation.

Backend endpoints require Firebase ID tokens. Student access is the default for authenticated accounts without a role claim; ADMIN access requires a server-managed Firebase `role=ADMIN` custom claim. Sensor ingestion requires `HYDROGUARD_SENSOR_API_KEY`. Authentication fails closed if Firebase or the sensor key is not configured. Set `HYDROGUARD_FIREBASE_PROJECT_ID` and use Application Default Credentials for the backend. No emergency contacts are seeded. Image fields currently accept HTTPS references only; uploads are not implemented.

Research export is available to admins at `GET /api/v1/research/export.csv` with optional `node_id`, `start`, and `end` filters. Missing actuals and error metrics remain blank. Alert records are included as event annotations; the export does not infer experimental correlations.

## Android build configuration

Debug API URL comes from Gradle property or environment variable `HYDROGUARD_API_BASE_URL` (emulator default `http://10.0.2.2:8000/`). Release builds require `HYDROGUARD_RELEASE_API_BASE_URL` using HTTPS and a private signing keystore configured through `KEYSTORE_PATH`, `STORE_PASSWORD`, `KEY_ALIAS`, and `KEY_PASSWORD`. Release logging is disabled. A signed bundle is not configured or published by default. Firebase Android configuration and production backend deployment must be supplied by the deployment owner.

See [hydroguard-backend/README.md](hydroguard-backend/README.md) for backend setup and API details.

## Current limitations

There is no established field dataset, field validation, validated optical-colour index, or evidence supporting real-world forecasting accuracy. Some app data is synthetic and exists only to support development. Do not treat demo alerts, readings, or synthetic model metrics as experimental results.

Admin WATER and student WATER use server-returned readings, history, forecasts, and alerts. Missing server data is shown as unavailable or insufficient; seeded Room readings and legacy demo risk visuals are not used in these operational routes. Admin hostel operations and student hostel services use the persisted API. The app's heuristic index is not a validated scientific or potable-water assessment.
