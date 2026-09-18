import argparse
import json

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.services.qa import answer_question


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask one Q&A question from inside the API container.")
    parser.add_argument("question")
    parser.add_argument("--email", default="viewer@cmpdi.local")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if user is None:
            raise SystemExit(f"user not found: {args.email}")
        response = answer_question(db, args.question, args.limit, user)
        print(json.dumps(response, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
