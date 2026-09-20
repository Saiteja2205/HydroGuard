# HydroGuard Demo Data

## IMPORTANT DISCLAIMER

**All data files in this directory are SYNTHETIC development data.**

- These are NOT real sensor measurements
- These are NOT representative of actual water quality conditions
- Do NOT use these datasets for real-world accuracy claims
- These datasets are for pipeline validation and development only

## Demo Files

### demo_water_quality.csv
- 30 days of synthetic water quality readings
- Used for initial pipeline testing
- Does NOT contain EC (Electrical Conductivity) or DO (Dissolved Oxygen)

### demo_water_quality_200days.csv
- 200 days of synthetic water quality readings
- Used for end-to-end ML training demonstration
- Contains all 6 parameters: pH, TDS, turbidity, temperature, EC, DO
- Simulates realistic trends with gradual changes and correlations

## Data Characteristics

The synthetic data simulates:
- Gradual seasonal trends (temperature increases over time)
- Correlated parameters (e.g., higher temperature → lower DO)
- Small daily noise/variation
- Realistic parameter ranges

## When Real Data is Available

Replace these demo files with actual sensor data from:
- ESP32 water quality sensors
- Manual water quality measurements
- Environmental monitoring stations

## Training on Synthetic Data

The `ml/training/train_all_models_demo.py` script uses this data to:
- Validate the complete ML pipeline
- Generate checkpoint files for API testing
- Demonstrate model training workflow

**Metrics from synthetic data training are NOT representative of real-world performance.**
