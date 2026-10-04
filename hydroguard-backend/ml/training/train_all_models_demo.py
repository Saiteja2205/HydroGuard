"""Compatibility entry point for current five-parameter development training.

The retired four-feature demonstration trainer is intentionally not callable;
this long-standing command now launches the versioned five-feature pipeline.
"""
from __future__ import annotations

from ml.training.train_five_parameter_development import main


if __name__ == "__main__":
    main()
