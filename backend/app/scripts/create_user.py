import argparse

from app.auth import create_user, find_user_by_email
from app.db import SessionLocal
from app.models import UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local demo user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", choices=[role.value for role in UserRole], required=True)
    parser.add_argument("--full-name", default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        existing = find_user_by_email(db, args.email)
        if existing is not None:
            print(f"user exists: id={existing.id} email={existing.email} role={existing.role.value}")
            return
        user = create_user(db, args.email, args.password, UserRole(args.role), args.full_name)
        print(f"user created: id={user.id} email={user.email} role={user.role.value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
