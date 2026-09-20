"""Forecast API endpoint for HydroGuard water quality forecasting."""

from fastapi import APIRouter, HTTPException

from app.schemas.readings import ForecastRequest, ForecastResponse
from ml.services import create_forecast_service, ForecastServiceConfig

router = APIRouter(tags=["forecast"])

# Global forecast service instance
forecast_service = None


def get_forecast_service() -> "ForecastService":
    """Get or create the forecast service instance."""
    global forecast_service
    if forecast_service is None:
        # Check if we're in four-parameter mode (demo checkpoints)
        import torch
        from pathlib import Path
        
        checkpoint_dir = Path("artifacts/checkpoints")
        lstm_checkpoint = checkpoint_dir / "lstm_water_quality_best.pt"
        
        four_param_mode = False
        if lstm_checkpoint.exists():
            checkpoint = torch.load(lstm_checkpoint, map_location='cpu')
            input_size = checkpoint.get('config', {}).get('input_size', 6)
            if input_size == 4:
                four_param_mode = True
        
        config = ForecastServiceConfig(
            four_parameter_mode=four_param_mode,
            parameters=("pH", "TDS", "turbidity", "temperature") if four_param_mode else ("pH", "TDS", "turbidity", "temperature", "EC", "DO"),
        )
        forecast_service = create_forecast_service(config)
    return forecast_service


@router.post("/forecast", response_model=ForecastResponse)
def generate_forecast(request: ForecastRequest) -> ForecastResponse:
    """Generate next-day water quality forecast using ensemble of models.

    Args:
        request: Forecast request with 30 days of historical readings

    Returns:
        Forecast response with ensemble prediction and individual model predictions

    Raises:
        HTTPException: If forecast generation fails
    """
    try:
        # Get forecast service
        service = get_forecast_service()

        # Check if we're in four-parameter mode
        is_four_param = len(service.config.parameters) == 4

        # For four-parameter mode, don't validate EC/DO
        if not is_four_param:
            request.validate_six_parameter_mode()

        # Load models if not already loaded
        if not service.models_loaded:
            try:
                service.load_models()
            except FileNotFoundError as e:
                raise HTTPException(
                    status_code=503,
                    detail=f"Forecast model checkpoint not found: {str(e)}",
                )

        # Convert readings to numpy array
        import numpy as np

        readings_array = []
        for reading in request.readings:
            if is_four_param:
                # Four-parameter mode: only pH, TDS, turbidity, temperature
                readings_array.append([
                    reading.pH,
                    reading.TDS,
                    reading.turbidity,
                    reading.temperature,
                ])
            else:
                # Six-parameter mode: include EC and DO
                readings_array.append([
                    reading.pH,
                    reading.TDS,
                    reading.turbidity,
                    reading.temperature,
                    reading.EC if reading.EC is not None else 0.0,
                    reading.DO if reading.DO is not None else 0.0,
                ])

        input_window = np.array(readings_array, dtype=np.float32)

        # Validate input shape and NaN values
        service.validate_input_shape(input_window)

        # Generate forecast
        forecast_result = service.generate_forecast(input_window)

        # Convert to response format
        prediction = forecast_result["prediction"]
        model_predictions = forecast_result["model_predictions"]
        weights = forecast_result["weights"]

        # Format model predictions
        formatted_model_predictions = {}
        for model_name, preds in model_predictions.items():
            formatted_model_predictions[model_name] = {
                "pH": preds["pH"],
                "TDS": preds["TDS"],
                "turbidity": preds["turbidity"],
                "temperature": preds["temperature"],
                "EC": preds.get("EC"),
                "DO": preds.get("DO"),
            }

        # Format weights
        formatted_weights = {}
        for param, param_weights in weights.items():
            formatted_weights[param] = {
                "LSTM": param_weights["LSTM"],
                "PatchTST": param_weights["PatchTST"],
                "TimeMixer": param_weights["TimeMixer"],
            }

        response = ForecastResponse(
            forecast_date=forecast_result["forecast_date"],
            prediction={
                "pH": prediction["pH"],
                "TDS": prediction["TDS"],
                "turbidity": prediction["turbidity"],
                "temperature": prediction["temperature"],
                "EC": prediction.get("EC"),
                "DO": prediction.get("DO"),
            },
            model_predictions=formatted_model_predictions,
            weights=formatted_weights,
        )

        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecast generation failed: {str(e)}")
