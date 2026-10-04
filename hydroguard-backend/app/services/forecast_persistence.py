"""Service for forecast persistence and retrieval.

Handles storing generated forecasts in the database and retrieving them for API responses.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db.repositories import ForecastRepository, NodeRepository


class ForecastPersistenceService:
    """Service for forecast persistence operations."""

    @staticmethod
    def store_forecast(
        db: Session,
        node_id: str,
        forecast_date: datetime,
        lstm_predictions: dict,
        patchtst_predictions: dict,
        timemixer_predictions: dict,
        ensemble_predictions: dict,
        weights: dict,
    ) -> Optional[int]:
        """Store a forecast in the database.

        Args:
            db: Database session
            node_id: Node identifier
            forecast_date: Date of the forecast
            lstm_predictions: LSTM model predictions
            patchtst_predictions: PatchTST model predictions
            timemixer_predictions: TimeMixer model predictions
            ensemble_predictions: Ensemble predictions
            weights: Model weights

        Returns:
            Forecast ID if successful, None otherwise
        """
        try:
            # Ensure node exists
            NodeRepository.get_or_create(
                db=db,
                node_id=node_id,
                name=f"Node {node_id}",
                location="Unknown",
                status="offline",
            )

            forecast = ForecastRepository.create(
                db=db,
                node_id=node_id,
                forecast_date=forecast_date,
                lstm_predictions=lstm_predictions,
                patchtst_predictions=patchtst_predictions,
                timemixer_predictions=timemixer_predictions,
                ensemble_predictions=ensemble_predictions,
                weights=weights,
            )
            return forecast.id
        except Exception as e:
            print(f"Error storing forecast: {e}")
            return None

    @staticmethod
    def get_forecasts(db: Session, node_id: str, limit: Optional[int] = None) -> list:
        """Get forecasts for a node.

        Args:
            db: Database session
            node_id: Node identifier
            limit: Maximum number of forecasts to return

        Returns:
            List of forecast records
        """
        return ForecastRepository.get_by_node(db, node_id, limit=limit)

    @staticmethod
    def get_latest_forecast(db: Session, node_id: str) -> Optional:
        """Get the latest forecast for a node.

        Args:
            db: Database session
            node_id: Node identifier

        Returns:
            Latest forecast record or None
        """
        return ForecastRepository.get_latest_by_node(db, node_id)
