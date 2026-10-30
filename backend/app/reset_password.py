"""Reset an account password locally (passwords are stored only as bcrypt hashes and cannot be retrieved).
Run on the Mac that hosts the app:  docker compose exec api python -m app.reset_password you@example.com
Lists the accounts if the email is not found. The new password is typed in this Terminal only."""

import getpass
import sys

from sqlalchemy import select

from .db import SessionLocal, init_db
from .models import User
from .security import hash_password


def main() -> None:
    init_db()
    with SessionLocal() as db:
        users = list(db.scalars(select(User).order_by(User.id)))
        if not users:
            print("This database has no accounts. Sign up at http://localhost:8080 (the first account is admin),\n"
                  "or move your data from the other Mac with scripts/db-export.sh and scripts/db-import.sh.")
            return
        email = (sys.argv[1] if len(sys.argv) > 1 else input("Account email: ")).strip().lower()
        u = db.scalar(select(User).where(User.email == email))
        if not u:
            print(f"No account {email} here. Accounts in this database: " + ", ".join(x.email for x in users))
            return
        pw = getpass.getpass("New password (8+ characters): ")
        if len(pw) < 8 or pw != getpass.getpass("Repeat: "):
            print("Not changed: too short or the two entries differ.")
            return
        u.password_hash = hash_password(pw)
        db.commit()
        print(f"Password reset for {email}{' (admin)' if u.is_admin else ''}.")


if __name__ == "__main__":
    main()
