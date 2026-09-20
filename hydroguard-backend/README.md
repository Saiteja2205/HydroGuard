# HydroGuard ML API

Python FastAPI backend for HydroGuard. This foundation serves **historical or simulated** development data only. It does **not** expose live sensor readings, and ML models (LSTM, PatchTST, TimeMixer) are not implemented yet.

## Prerequisites

- Python 3.10 or newer

## Create the virtual environment

From PowerShell, in this folder:

```powershell
cd Z:\EPICS\Hydroguard\hydroguard-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
cd hydroguard-backend
python3 -m venv .venv
source .venv/bin/activate
```

## Install requirements

With the virtual environment activated:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run FastAPI

From `hydroguard-backend` with the virtual environment activated:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## URLs

| Resource | URL |
| --- | --- |
| Health | http://127.0.0.1:8000/api/v1/health |
| Latest reading (example) | http://127.0.0.1:8000/api/v1/nodes/node_overhead_a/readings/latest |
| Swagger UI | http://127.0.0.1:8000/docs |
| OpenAPI JSON | http://127.0.0.1:8000/openapi.json |

## Notes

- `ec` and `do` are nullable because those physical sensors have not been purchased yet.
- `sensors_connected` is always `false` in this step.
- `models_loaded` flags stay `false` until models are added in a later step.
