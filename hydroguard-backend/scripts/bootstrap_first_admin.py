"""One-time trusted operator command to provision HydroGuard's first admin."""

import argparse
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import firebase_admin
from firebase_admin import auth as firebase_auth

from app.core.auth import _firebase_app
from app.db.auth_models import HydroGuardUser
from app.db.database import SessionLocal, init_db
from app.services.auth_service import bootstrap_first_admin


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision the first HydroGuard administrator from an existing verified Firebase account."
    )
    parser.add_argument("email", help="Verified Firebase email for the first administrator")
    args = parser.parse_args()

    project_id = os.environ.get("HYDROGUARD_FIREBASE_PROJECT_ID", "").strip()
    if not project_id:
        print("HYDROGUARD_FIREBASE_PROJECT_ID is not set.", file=sys.stderr)
        return 2

    app = None
    try:
        app = _firebase_app()
        if app.project_id != project_id:
            print("Firebase Admin initialized for a different project.", file=sys.stderr)
            return 1

        try:
            firebase_user = firebase_auth.get_user_by_email(args.email.strip(), app=app)
        except firebase_auth.UserNotFoundError:
            print("Firebase user not found. Have the account sign in once, then retry.", file=sys.stderr)
            return 1

        init_db()
        with SessionLocal() as db:
            account: HydroGuardUser = bootstrap_first_admin(db, firebase_user)

        print(f"First HydroGuard administrator provisioned. Firebase UID: {account.firebase_uid}")
        return 0
    except Exception as exc:
        print(f"First administrator provisioning failed ({type(exc).__name__}).", file=sys.stderr)
        return 1
    finally:
        if app is not None:
            firebase_admin.delete_app(app)


if __name__ == "__main__":
    raise SystemExit(main())
