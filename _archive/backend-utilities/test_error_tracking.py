from datetime import datetime, timezone
from app.db.database import get_db_context, init_db
from app.db.repositories import NodeRepository, SensorReadingRepository, ForecastRepository, ModelErrorRepository
from app.services.error_tracking import ErrorTrackingService

init_db()

with get_db_context() as db:
    # Ensure node exists
    NodeRepository.get_or_create(
        db=db,
        node_id="node_overhead_a",
        name="Overhead Tank A",
        location="Hostel Block A",
    )

    # Create a test forecast
    forecast_date = datetime.now(timezone.utc)
    forecast = ForecastRepository.create(
        db=db,
        node_id="node_overhead_a",
        forecast_date=forecast_date,
        lstm_predictions={"pH": 7.0, "TDS": 180.0, "turbidity": 1.0, "temperature": 22.0, "optical_colour_index": 0.50},
        patchtst_predictions={"pH": 7.1, "TDS": 182.0, "turbidity": 1.1, "temperature": 22.2, "optical_colour_index": 0.52},
        timemixer_predictions={"pH": 7.05, "TDS": 181.0, "turbidity": 1.05, "temperature": 22.1, "optical_colour_index": 0.51},
        ensemble_predictions={"pH": 7.05, "TDS": 181.0, "turbidity": 1.05, "temperature": 22.1, "optical_colour_index": 0.51},
        weights={
            "pH": {"LSTM": 0.33, "PatchTST": 0.33, "TimeMixer": 0.34},
            "TDS": {"LSTM": 0.33, "PatchTST": 0.33, "TimeMixer": 0.34},
            "turbidity": {"LSTM": 0.33, "PatchTST": 0.33, "TimeMixer": 0.34},
            "temperature": {"LSTM": 0.33, "PatchTST": 0.33, "TimeMixer": 0.34},
            "optical_colour_index": {"LSTM": 0.33, "PatchTST": 0.33, "TimeMixer": 0.34},
        },
    )
    print(f"Created forecast ID: {forecast.id}")

    # Create actual reading for the same date
    actual_reading = SensorReadingRepository.create(
        db=db,
        node_id="node_overhead_a",
        timestamp=forecast_date,
        ph=7.1,  # Actual differs from prediction
        tds=185.0,
        turbidity=1.15,
        temperature=22.5,
        optical_colour_index=0.53,
        source="SIMULATED",
    )
    print(f"Created actual reading ID: {actual_reading.id}")

    # Manually create error records (direct test of storage)
    # This is controlled test data, not real-world performance
    error1 = ModelErrorRepository.create(
        db=db,
        node_id="node_overhead_a",
        forecast_id=forecast.id,
        forecast_date=forecast_date,
        model_name="LSTM",
        parameter="pH",
        predicted_value=7.0,
        actual_value=7.1,
        absolute_error=0.1,
        squared_error=0.01,
        mae=0.1,
        rmse=0.1,
    )
    print(f"Created LSTM pH error ID: {error1.id}")

    error2 = ModelErrorRepository.create(
        db=db,
        node_id="node_overhead_a",
        forecast_id=forecast.id,
        forecast_date=forecast_date,
        model_name="PatchTST",
        parameter="pH",
        predicted_value=7.1,
        actual_value=7.1,
        absolute_error=0.0,
        squared_error=0.0,
        mae=0.0,
        rmse=0.0,
    )
    print(f"Created PatchTST pH error ID: {error2.id}")

    error3 = ModelErrorRepository.create(
        db=db,
        node_id="node_overhead_a",
        forecast_id=forecast.id,
        forecast_date=forecast_date,
        model_name="TimeMixer",
        parameter="pH",
        predicted_value=7.05,
        actual_value=7.1,
        absolute_error=0.05,
        squared_error=0.0025,
        mae=0.05,
        rmse=0.05,
    )
    print(f"Created TimeMixer pH error ID: {error3.id}")

    # Verify errors were stored
    errors = ModelErrorRepository.get_by_node(db, "node_overhead_a", limit=10)
    print(f"Total errors for node: {len(errors)}")
    for error in errors:
        print(f"  {error.model_name} {error.parameter}: predicted={error.predicted_value}, actual={error.actual_value}, mae={error.mae}, rmse={error.rmse}")

print("Error tracking test complete")
