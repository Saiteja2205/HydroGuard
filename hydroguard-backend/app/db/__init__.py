"""Database module for HydroGuard backend.

Provides SQLAlchemy ORM models, database connection management,
and repository pattern for data access.
"""

# Import models first to ensure they are registered with SQLAlchemy
from app.db.models import (
    Node,
    SensorReading,
    Forecast,
    ModelError,
    Alert,
    EnsembleWeight,
    SensorCalibration,
)

# Import database functions
from app.db.database import get_db, init_db

# Import repositories
from app.db.repositories import (
    NodeRepository,
    SensorReadingRepository,
    ForecastRepository,
    ModelErrorRepository,
    AlertRepository,
    EnsembleWeightRepository,
    SensorCalibrationRepository,
)

__all__ = [
    "get_db",
    "init_db",
    "Node",
    "SensorReading",
    "Forecast",
    "ModelError",
    "Alert",
    "EnsembleWeight",
    "SensorCalibration",
    "NodeRepository",
    "SensorReadingRepository",
    "ForecastRepository",
    "ModelErrorRepository",
    "AlertRepository",
    "EnsembleWeightRepository",
    "SensorCalibrationRepository",
]
