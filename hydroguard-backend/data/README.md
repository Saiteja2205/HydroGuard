# HydroGuard Development Data

## IMPORTANT DISCLAIMER

**All data files in this directory are SIMULATED development data.**

- These are NOT real sensor measurements
- These are NOT representative of actual water quality conditions
- Do NOT use these datasets for real-world accuracy claims
- These datasets are for pipeline validation and development only

## Demo Files

### demo_water_quality.csv
- 30 days of synthetic water quality readings
- Used for initial pipeline testing
- Does NOT contain EC (Electrical Conductivity) or DO (Dissolved Oxygen)

### development_water_quality_200_observations.csv
- Exactly 200 chronologically ordered simulated observations.
- `source=SIMULATED`, `dataset_type=DEVELOPMENT`, `real_sensor_data=false`.
- Active model features: pH, TDS, turbidity, temperature, optical_colour_index.
- Includes simulated TCS34725 raw RGB/clear fields. The optical index is an uncalibrated synthetic feature.
- This is a **200-observation development dataset**, not real sensor data.

### Legacy dataset
`demo_water_quality_200days.csv` is retained as historical test input only. Its old feature columns are not used by the active five-parameter model pipeline.

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

The `ml/training/train_all_models_demo.py` compatibility command now launches the five-parameter trainer on the 200-observation development dataset to:
- Validate the complete ML pipeline
- Generate checkpoint files for API testing
- Demonstrate model training workflow

**Metrics from synthetic data training are NOT representative of real-world performance.**
