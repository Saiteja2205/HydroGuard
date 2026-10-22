# HydroGuard Project Structure

This document describes the active source tree. The Android build compiles the Java/XML implementation under `com/aistudio/hydroguard/wxqpzx`. Legacy uncompiled Kotlin files under `com/example` and obsolete stray debug utilities have been cleaned up; their history remains safely preserved in earlier Git checkpoints and tags.

## Root

| Directory or file | Purpose | Used by | Classification |
|---|---|---|---|
| `app/` | Java/XML Android client, its resources, and tests | Students, administrators, Android build | Runtime source and tests |
| `hydroguard-backend/` | FastAPI service, database, API, forecasting code, model artifacts, data, and tests | Android client, sensor/API integrations, research workflow | Runtime, development, and research |
| `gradle/` | Gradle wrapper and version catalog | Android build | Development/build tooling |
| `assets/` | Contains only the `.aistudio/.gitignore` marker; no application or research assets were present | None currently identified | Tooling placeholder |
| `.idea/` | Android Studio project settings and shared run configurations; local workspace state was removed | Android Studio | Development configuration |
| `.git/` | Repository history and metadata | Git | Version control |
| `build.gradle.kts` | Root Gradle plugin declarations | Android build | Build configuration |
| `settings.gradle.kts` | Plugin/dependency repositories and `:app` inclusion | Android build | Build configuration |
| `gradle.properties` | Gradle and Android build options | Android build | Build configuration |
| `local.properties` | Machine-specific Android SDK path; ignored and not tracked by Git | Local Android build | Local development configuration |
| `gradlew`, `gradlew.bat` | Gradle wrapper entry points for Unix-like shells and Windows | Developers/CI | Build tooling |
| `.gitignore` | Excludes local caches, build outputs, credentials, and machine settings | Git | Repository configuration |
| `.env.example` | Placeholder environment variable example; no real API key | AI Studio configuration | Development configuration |
| `.dev-auth.env` | Local development-only authentication settings; ignored and untracked | Local debug Android/backend use | Development secret configuration |
| `firestore.rules` | Firebase Firestore authorization rules for the Firebase data surface | Firebase deployment | Runtime security configuration |
| `metadata.json` | AI Studio app name, description, and capability metadata | AI Studio | Tooling metadata |
| `README.md` | Product behavior, component overview, setup, and limitations | Developers and reviewers | Documentation |
| `PROJECT_STRUCTURE.md` | This source-tree inventory | Developers and reviewers | Documentation |
| `VIVA_PROJECT_STRUCTURE.md` | Plain-language explanations for project presentation | Student presenter | Documentation |

## Android application (`app/`)

| Path | Purpose | Used by | Classification |
|---|---|---|---|
| `app/build.gradle.kts` | Android Java, Firebase, dependencies, debug/release flags, and test setup | Gradle | Build configuration |
| `app/proguard-rules.pro` | Shrinker rules for Android release builds | Gradle release build | Build configuration |
| `app/src/main/AndroidManifest.xml` | Application identity, components, and platform permissions | Android OS | Runtime configuration |
| `app/src/main/java/com/aistudio/hydroguard/wxqpzx/MainActivity.java` | Java sign-in entry point and Google Credential Manager flow | Android OS | Runtime source |
| `app/src/main/java/com/aistudio/hydroguard/wxqpzx/DashboardActivity.java` | Student/admin navigation, monitoring, forecasting, and hostel workflows | Students and administrators | Runtime source |
| `.../data/api/` | Retrofit service, URL/auth interceptors, and API error handling | Android client/backend | Runtime source and API contract |
| `.../data/database/` | Java Room entities, database, and DAOs for local cache/offline state | Android client | Runtime source |
| `.../data/repository/` | Firebase auth, debug session policy, and local/remote data coordination | Android client | Runtime source |
| `.../data/service/` | Client-side water-quality index calculation and local alert notifications (channel, deduplication) | Android client | Runtime source |
| `.../ui/` | Water monitoring screen controller, alert list adapter, and chart wiring (MPAndroidChart) | Android screens | Runtime source |
| `.../ui/viewmodel/` | Java UI state and repository coordination | Android screens | Runtime source |
| `app/src/main/res/` | XML layouts, launcher icons, strings, themes, backup and network policies | Android OS and UI | Runtime resources |
| `app/src/debug/` | Debug-only manifest and network security policy | Debug APK | Development/runtime configuration |
| `app/src/test/java/com/aistudio/hydroguard/wxqpzx/` | Java auth policy and index unit tests | Android test runner | Tests |
| `app/src/androidTest/` | Instrumented Android test source (none in the active Java implementation) | Android device test runner | Tests |

## Backend (`hydroguard-backend/`)

| Path | Purpose | Used by | Classification |
|---|---|---|---|
| `app/main.py` | Creates FastAPI application, initializes database, and registers API routes | Uvicorn and API clients | Runtime source |
| `app/api/` | Health, reading, forecast, node, alert, threshold, hostel, and research-export endpoints | Android, sensors, administrators, research | Runtime source/API |
| `app/core/` | Authentication and access-control helpers | API routes | Runtime security source |
| `app/db/` | SQLAlchemy database, tables, repositories, initialization, and seeding | API/services | Runtime source and database |
| `app/schemas/` | Pydantic request and response contracts | API routes and clients | Runtime source/API |
| `app/services/` | Forecast persistence, alerts, and error tracking logic | API routes | Runtime source |
| `ml/data/` | Five-parameter data validation, loading, windows, and preprocessing | Forecasting and research workflow | Runtime/research source |
| `ml/models/` | LSTM, PatchTST, and TimeMixer model definitions | Forecast service/training | Runtime/research source |
| `ml/prediction/` | Model-specific checkpoint loading and prediction helpers | Forecast service | Runtime source |
| `ml/ensemble/` | Adaptive parameter-specific ensemble and weighting | Forecast service | Runtime/research source |
| `ml/services/` | Forecast orchestration and versioned checkpoint selection | Forecast API | Runtime source |
| `ml/training/` | Training and evaluation scripts, including five-parameter development training | Research workflow | Research/development source |
| `artifacts/checkpoints/` | Three active `_5param_v1` checkpoints plus retained legacy `best` and `last` files | Forecast runtime and historical workflows | Runtime/research artifacts |
| `artifacts/results/` | Five-parameter evaluation and model metrics JSON | Research and forecast weighting | Research artifacts |
| `data/` | Demo CSVs and the 200-observation simulated five-parameter development dataset with provenance metadata | Tests, training, demonstrations | Development/research data |
| `tests/` | API, database, authentication, model, ensemble, and research-contract tests | Pytest | Tests |
| `requirements.txt` | Python dependencies for API, persistence, ML, and tests | Python environment | Development/runtime configuration |
| `README.md`, `data/README.md` | Setup, API/data behavior, provenance, limitations, and run instructions | Developers/researchers | Documentation |
| `*_IMPLEMENTATION_REPORT.md`, `ML_DEMO_*_REPORT.md` | Historical implementation and evaluation notes; some refer to older model contracts and should be read as historical records | Review/research | Research documentation |
| `scripts/` | Local database inspection, seeding, single-hostel migration, and development utilities | Developers | Development tools |

## Active ML contract and retained legacy artifacts

The active forecast parameters are `pH`, `TDS`, `turbidity`, `temperature`, and `optical_colour_index`. `ForecastServiceConfig` names the `_5param_v1` LSTM, PatchTST, and TimeMixer checkpoints. The adaptive ensemble combines these model forecasts. The five-parameter CSV is explicitly simulated development data, not field evidence.

The legacy `*_best.pt` checkpoints have four input/output features; the `*_last.pt` checkpoints have six. Their hashes are all distinct from one another. They were not removed because historical reports and training code refer to the generic `best`/`last` names, and their continued value to older research workflows is not established. The active service selects only the three `_5param_v1.pt` files. The legacy checkpoints remain a review item.

## Cleanup notes

Removed local generated directories: `.android-cache/`, `.android-user/`, `.java-user/`, `.kotlin/`, and `.robolectric-home/`. Removed `.idea/workspace.xml` and `.idea/caches/deviceStreaming.xml`; kept the remaining Android Studio project settings and code style. Temporary Gradle/Robolectric caches and generated Android build outputs created for verification were also removed; the APK is not retained in this source tree. `assets/` was retained because it contains a tooling marker, although it has no substantive assets. No empty project source directories were removed. Empty structural directories under `.git/` were retained.

`local.properties` is ignored and not tracked. `.dev-auth.env` is ignored and not tracked; its values are not reproduced here. Git history was not rewritten. At inspection, `.git/objects` used about 213.57 MiB. The largest object was a 203.54 MiB Robolectric `android-all-instrumented` JAR formerly stored under `.java-user/.m2/repository/...`; it is present only in unreachable historical trees, not the current working tree or active refs. Other large objects are the retained legacy and active model checkpoints. No Git history operation was performed.

## Review items

- `firestore.rules` currently allows unauthenticated document creation in `SensorReadings` and `Alerts`. Comments mention ESP32/API verification, but those rules do not enforce such verification themselves; confirm the intended deployment path before using direct Firestore writes.
- The retained four-feature `best` and six-feature `last` checkpoints are not active, but their value to older research runs should be decided separately.
- `.git` retains the unreachable 203.54 MiB Robolectric JAR blob; history cleanup was intentionally not attempted.
