"""
Creates the single application user. Run manually, not exposed via the API
(see docs/auth-architecture.md — no public /register endpoint by design).

Usage (inside the backend container or a local venv with DATABASE_URL set):
    python -m scripts.create_user user@example.com
"""

import sys
from getpass import getpass

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.risk_settings import RiskSettings
from app.models.user import User


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.create_user <email>")
        sys.exit(1)

    email = sys.argv[1]
    password = getpass("Password: ")
    confirm = getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = User(email=email, hashed_password=hash_password(password))
        db.add(user)
        db.flush()  # get user.id before creating dependent rows

        # Default risk settings so the user isn't left in a half-configured
        # state; these are meant to be edited via the API afterwards.
        db.add(
            RiskSettings(
                user_id=user.id,
                account_balance=0,
                risk_percent=1,
                max_exposure_percent=5,
                min_risk_reward=1.5,
            )
        )
        db.commit()
        print(f"User created: {user.id} ({user.email})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
