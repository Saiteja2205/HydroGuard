import os
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))
os.chdir(str(backend_root))

from app.db.seed import seed_development_dataset, seed_devices
from app.db.database import get_db_context

with get_db_context() as db:
    count = seed_development_dataset(db)
    seed_devices(db)
    print("Seeding complete: " + str(count) + " readings created")
