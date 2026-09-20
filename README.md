# HydroGuard AI
### IoT-Based Smart Water Quality Monitoring & Forecasting System

HydroGuard AI is an enterprise-grade Smart City monitoring and predictive analytical platform designed as an **EPICS (Engineering Projects in Community Service)** college hostel project. The application connects directly to real-time ESP32 IoT nodes, monitors physical water metrics, forecasts pollution risks using a machine learning engine, alerts administrations of threshold violations, and streamlines hostel maintenance.

---

## 🚀 Key Features

### 1. Multi-Role Dashboards
*   **ADMIN COMMAND CONSOLE:** 
    *   Live telemetry metrics and circular gauges.
    *   Dynamic area/line charts with multi-variable parameters.
    *   **AI Predictor Desk:** Real-time ML models detailing contamination index and confidence intervals.
    *   **Alert & Ticket Desk:** Mark student feedback resolved, assign maintenance teams, and review audits.
    *   **Calibrate Sensors:** Directly tune trigger parameters (pH limits, turbidity boundaries).
    *   **Weekly Audit Builder:** Generate and save formal system reports.
*   **STUDENT RESIDENT PORTAL:**
    *   Immediate, clean water safety score (Excellent, Good, Warning, Critical).
    *   Simplified physical metric bento cards (pH, Turbidity, TDS, Temp).
    *   Active admin safety announcements and notices.
    *   **Dual Reporting Wizard:** Submit detailed feedback on water quality or lodging maintenance.

### 2. Machine Learning Predictive Engine
*   Integrates with **Google Gemini 3.5 Flash** models to continuously compute 24-hour and 7-day risk assessments, parse organic pollution probabilities, and construct actionable administration remediation guides.
*   Includes a backup **Random Forest / Regression** mimic model for full offline-first execution, allowing instant analytics even during network blackouts.

### 3. ESP32 IoT Stream Simulator
*   Simulates the real-world connection of overhead and mess water tanks by periodically inserting physical reading fluctuations.
*   Automatically logs system-wide alarms if chemistry limits are breached.

---

## 🛠️ Tech Stack
*   **Language:** Kotlin
*   **UI Toolkit:** Jetpack Compose (Material Design 3)
*   **Local Caching:** Room SQLite Database (DAO & Flow Streams)
*   **Navigation:** Jetpack Navigation Compose
*   **Networking:** Retrofit + OkHttp + Moshi Serializer
*   **Core Model:** Google Gemini REST API (Server-Side)
*   **Sign-In:** Role-Based Session Architecture

---

## 📁 Project Architecture & Package Structure
```text
/app/src/main/java/com/example/
│
├── MainActivity.kt                  # NavHost Router and Edge-to-Edge wrapper
│
├── data/
│   ├── database/
│   │   ├── Entities.kt             # Room Tables (Users, Readings, Alerts, Feedbacks...)
│   │   ├── Daos.kt                 # Reactive Flow queries
│   │   └── AppDatabase.kt          # SQLite Database configuration
│   │
│   └── repository/
│       └── HydroRepository.kt      # Mock seeder, ESP32 simulator, and trigger alarms
│
├── service/
│   └── GeminiForecastService.kt    # Retrofit REST API connector for Gemini 3.5 Flash
│
└── ui/
    ├── theme/
    │   ├── Color.kt                # Corporate primary blue and status indicators
    │   ├── Theme.kt                # Light and Dark theme builders
    │   └── Type.kt                 # Typography pairings
    │
    ├── components/
    │   └── WaterComponents.kt      # Speedometers, Bento sparklines, and Canvas charts
    │
    └── screens/
        ├── LoginScreen.kt          # Institutional login with Dev shortcuts
        ├── StudentDashboardScreen.kt # Purity gauge, live readings, and forms
        ├── AdminDashboardScreen.kt   # Command charts, settings, and triage
        └── FeedbackScreen.kt       # Dual category submission form
```

---

## ☁️ Firebase Architecture & Cloud Configuration

### Collection Schemas
1.  **Users:** `{ email, name, role, hostelBlock, roomNumber, createdAt }`
2.  **SensorNodes:** `{ nodeId, name, location, status, lastSeen }`
3.  **SensorReadings:** `{ id, nodeId, timestamp, ph, turbidity, tds, temperature, flowRate }`
4.  **Predictions:** `{ nodeId, timestamp, contaminationProbability, riskScore, confidence, predictionText }`
5.  **Alerts:** `{ id, nodeId, timestamp, parameterName, value, thresholdLimit, riskLevel, recommendation, isResolved }`
6.  **WaterFeedback:** `{ id, rating, issueType, description, imagePath, hostelBlock, roomNumber, status, remarks }`
7.  **HostelFeedback:** `{ id, category, priority, description, imagePath, hostelBlock, roomNumber, status, remarks }`

---

## ⚙️ Setup and Installation Instructions

### Prerequisites
1.  Android Studio (Ladybug or newer).
2.  Google Gemini API Key configured in the Google AI Studio Console.

### Step 1: Configure Secret Environment Variables
Do **not** hardcode credentials in source code. HydroGuard uses the `Secrets Gradle Plugin` to map secrets securely:
1.  Open the **Secrets Panel** in Google AI Studio.
2.  Inject your `GEMINI_API_KEY`.
3.  The platform automatically resolves this variable at build time in `BuildConfig.GEMINI_API_KEY`.

### Step 2: Build and Deploy
1.  Sync the project with Gradle.
2.  Compile the application onto an Android emulator or dynamic device.
3.  Use the **Dev Test Shortcuts** on the login page for instant authentication:
    *   `Demo Student` -> Accesses block water safety, active advisories, and the report wizard.
    *   `Demo Admin` -> Accesses full-bleed Canvas area charts, alarm dismissals, student tickets, and sensor calibration.
