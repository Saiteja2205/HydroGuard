# HydroGuard Project Structure: Viva Notes

Use these short explanations to describe the files that matter to the project. The source has an Android app, a FastAPI backend, and a research forecasting workflow.

| Folder/File | Purpose | What I should say to sir |
|---|---|---|
| `app/` | Android application source, resources, and tests | “This is the mobile application used by students and administrators.” |
| `app/src/main/java/` | Java application code | “The Android screens and app logic are written in Java.” |
| `app/src/main/java/com/aistudio/hydroguard/wxqpzx/MainActivity.java` | Starts sign-in and Google Credential Manager | “This entry point lets a verified Google account sign in to HydroGuard.” |
| `app/src/main/java/com/aistudio/hydroguard/wxqpzx/DashboardActivity.java` | Student and administrator navigation and workflows | “This activity opens the correct role-based destinations and connects them to the backend.” |
| `app/src/main/java/com/aistudio/hydroguard/wxqpzx/data/api/` | Retrofit client, endpoint interface, and API error handling | “These files let the Android app exchange structured data with the backend.” |
| `app/src/main/java/com/aistudio/hydroguard/wxqpzx/data/database/` | Java Room entities, database, and DAOs | “Room stores a local cache and supports offline reads; the backend remains authoritative for server data.” |
| `app/src/main/java/com/aistudio/hydroguard/wxqpzx/data/repository/` | Firebase authentication and local/remote data coordination | “Repositories connect sign-in and app screens to remote services and local data.” |
| `app/src/main/java/com/aistudio/hydroguard/wxqpzx/data/service/` | Water-quality index calculation | “This contains the app’s calculation service; the index is an application measure, not a water-safety certification.” |
| `app/src/main/res/` | XML layouts, icons, text, themes, and platform resources | “The screen layouts and Android resources are XML, separate from Java logic.” |
| `app/src/debug/` | Debug-only settings | “This folder contains settings that apply only to development builds.” |
| `app/src/test/` | Unit and Robolectric tests | “These tests check app logic without requiring a physical phone.” |
| `app/src/androidTest/` | Instrumented tests | “These tests are intended to run on an Android device or emulator.” |
| `hydroguard-backend/` | Backend API, database, ML workflow, research files, and tests | “The backend receives and stores project data and provides services used by the app.” |
| `hydroguard-backend/app/main.py` | Creates the FastAPI service and registers routes | “This starts the backend application and connects its API sections.” |
| `hydroguard-backend/app/api/` | Health, water readings, forecasts, alerts, hostel services, and research export endpoints | “These files expose backend services to the Android app and authorized integrations.” |
| `hydroguard-backend/app/core/` | Authentication and authorization | “This checks who can access protected backend features.” |
| `hydroguard-backend/app/db/` | Database setup, models, and repositories | “This folder defines how backend records are stored and retrieved.” |
| `hydroguard-backend/app/schemas/` | Validated API request and response shapes | “Schemas keep the data sent to and from the API consistent.” |
| `hydroguard-backend/app/services/` | Backend workflows such as alerts and forecast evaluation persistence | “These services implement operations shared by the API endpoints.” |
| `hydroguard-backend/ml/data/` | Data validation, preprocessing, and time-window generation | “This prepares chronological water-quality observations for forecasting.” |
| `hydroguard-backend/ml/models/` | LSTM, PatchTST, and TimeMixer model definitions | “These are the three forecasting model architectures used in the ensemble.” |
| `hydroguard-backend/ml/prediction/` | Checkpoint loading and model prediction helpers | “These files load trained model parameters and produce forecasts.” |
| `hydroguard-backend/ml/ensemble/` | Adaptive ensemble and model weighting | “The ensemble combines the three model outputs and can adjust weights using recorded errors.” |
| `hydroguard-backend/ml/services/forecast_service.py` | Loads the selected models and orchestrates predictions | “This service coordinates the forecasting workflow and selects the active five-parameter checkpoints.” |
| `hydroguard-backend/ml/training/` | Model training and evaluation scripts | “These scripts support the research and development workflow; they are not needed to retrain models during normal app use.” |
| `hydroguard-backend/artifacts/checkpoints/` | Saved model weights | “A checkpoint stores learned model parameters so forecasts can be generated without training the model again.” |
| `*_5param_v1.pt` | Active five-parameter checkpoints for the three models | “These are the versioned checkpoints selected by the current backend for the five-feature contract.” |
| `*_best.pt` and `*_last.pt` | Retained older checkpoint files | “These older files are preserved because historical scripts and reports still refer to them; the active service defaults use the versioned five-parameter files.” |
| `hydroguard-backend/ml/ensemble/adaptive_ensemble.py` | Combines model results by parameter | “This combines LSTM, PatchTST, and TimeMixer predictions, with weights that can be updated from observed errors.” |
| `hydroguard-backend/artifacts/results/` | Saved model metrics and five-parameter evaluation | “These JSON files preserve evaluation results and checkpoint provenance for research review.” |
| `hydroguard-backend/data/` | Example datasets and simulated development observations | “The dataset supports development and reproducibility; simulated data is clearly distinguished from real sensor evidence.” |
| `development_water_quality_200_observations.csv` | 200-row simulated five-parameter training dataset | “This dataset is used by the development training workflow; it is not a field-measured dataset.” |
| `*.metadata.json` | Dataset parameters and provenance notes | “This metadata records how the dataset was created and its limitations.” |
| `hydroguard-backend/tests/` | Backend, API, database, authentication, and ML tests | “These tests help check that backend features and model contracts continue to work.” |
| `hydroguard-backend/requirements.txt` | Python packages needed by the backend | “This lists the Python dependencies required to set up the backend environment.” |
| `hydroguard-backend/README.md` | Backend setup, API, data contract, and limitations | “This explains how to run the backend and what the data and model results mean.” |
| `hydroguard-backend/*IMPLEMENTATION_REPORT.md` | Development and research reports | “These reports record implementation history; older ones may describe earlier model contracts.” |
| `gradle/` | Gradle wrapper and dependency version catalog | “Gradle manages Android build tools and dependency versions.” |
| `gradlew`, `gradlew.bat` | Gradle launchers | “These let developers run the project’s Gradle tasks on different operating systems.” |
| `settings.gradle.kts` | Declares repositories and Android modules | “This tells Gradle which modules and plugin repositories belong to the project.” |
| `build.gradle.kts` | Root plugin configuration | “This configures Gradle plugins shared by the Android project.” |
| `app/build.gradle.kts` | Android app build, dependencies, debug/release options, and test setup | “This defines how the Android app is compiled and which libraries it uses.” |
| `firestore.rules` | Firebase Firestore access rules | “These rules restrict Firebase data access according to the configured security policy.” |
| `.env.example` | Placeholder environment variable example | “This shows the expected environment variable name without storing a real key.” |
| `.dev-auth.env` | Ignored local development authentication settings | “This is local-only debug configuration and is excluded from Git so a development token is not committed.” |
| `local.properties` | Local Android SDK location | “This points Gradle to the SDK on this machine and is ignored because the path differs for each developer.” |
| `.gitignore` | Excludes generated files and local secrets | “This prevents local build outputs and credentials from being included in version control.” |
| `.idea/` | Android Studio project settings | “This contains IDE project settings; the machine-specific workspace file was removed.” |
| `.git/` | Repository history | “Git records source history here; it was preserved without rewriting or cleaning historical objects.” |
| `assets/` | Currently only contains an AI Studio marker file | “There are no substantive application images or research datasets in this folder right now.” |
| `README.md` | Project overview, navigation, data handling, and limitations | “This is the main guide to the project’s components and its scientific limitations.” |
| `PROJECT_STRUCTURE.md` | Detailed directory inventory | “This document explains how the cleaned source tree is organized.” |

### Additional project files

| Folder/File | Purpose | What I should say to sir |
|---|---|---|
| `metadata.json` | AI Studio app name, description, and capability metadata | “This records the app’s name and setup metadata for AI Studio.” |
| `app/src/main/java/com/aistudio/hydroguard/wxqpzx/DashboardActivity.java` | Student and admin reporting, issue tracking, service directory, and profiles | “Students can report and follow hostel issues, view verified Warden or Security contacts, and use hostel services; administrators manage reports and contact verification.” |
| `hydroguard-backend/=2.7.0` | Tracked pip output excerpt for a CPU PyTorch wheel download | “This is a saved environment setup log, not code that runs as part of the app.” |

## Short project explanation

“HydroGuard has an Android app for students and administrators, a FastAPI backend that stores and serves project data, and an ML research workflow that forecasts five water-quality parameters. The backend uses LSTM, PatchTST, and TimeMixer forecasts in an adaptive ensemble. The saved checkpoints let the backend load trained models without retraining them. The included 200-observation dataset is simulated development data, so its evaluation is not a claim of field accuracy or drinking-water safety.”

## Notes for likely viva questions

- `metadata.json`: “This records the app name, description, and AI Studio capability metadata.”
- The active `*_5param_v1.pt` checkpoints use five features. The retained `*_best.pt` files have four features, while `*_last.pt` files have six; the backend does not select them by default. The files are distinct, and they remain because old research reports and training code mention them.
- `hydroguard-backend/=2.7.0`: “This is a saved pip output excerpt for a CPU PyTorch wheel download, not runtime code.”
- `firestore.rules`: “This file defines Firebase Firestore access. Its current SensorReadings and Alerts rules allow direct creates without Firebase authentication; the ESP32/API verification mentioned in comments must happen elsewhere if those writes are used.”
