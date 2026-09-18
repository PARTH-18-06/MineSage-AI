from app.auth import create_user, find_user_by_email
from app.config import settings
from app.db import SessionLocal
from app.models import UserRole


def main() -> None:
    db = SessionLocal()
    try:
        existing = find_user_by_email(db, settings.default_admin_email)
        if existing is not None:
            print(f"admin exists: id={existing.id} email={existing.email} role={existing.role.value}")
            return

        user = create_user(
            db,
            email=settings.default_admin_email,
            password=settings.default_admin_password,
            role=UserRole.admin,
            full_name=settings.default_admin_full_name,
        )
        print(f"admin created: id={user.id} email={user.email} role={user.role.value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
