from database import SessionLocal
from models import User, Transaction
from auth import hash_password
from datetime import datetime, timedelta
import random


DEMO_USERS = [
    {
        "username": "jsmith",
        "full_name": "James Smith",
        "email": "j.smith@example.com",
        "password": "Pass1234!",
        "account_number": "4820-0011-2233",
        "balance": 24_850.75,
    },
    {
        "username": "agarcia",
        "full_name": "Ana Garcia",
        "email": "a.garcia@example.com",
        "password": "Garcia99!",
        "account_number": "4820-0011-5566",
        "balance": 8_340.20,
    },
    {
        "username": "admin",
        "full_name": "System Administrator",
        "email": "admin@cerberusbank.gov",
        "password": "Admin2024!",
        "account_number": "4820-0000-0001",
        "balance": 1_250_000.00,
    },
]

TRANSACTION_TEMPLATES = [
    ("credit", "Direct Deposit - Payroll", 3_200.00),
    ("debit", "Online Bill Pay - Electric Co.", -148.50),
    ("debit", "Grocery Store Purchase", -87.32),
    ("credit", "ACH Transfer Received", 500.00),
    ("debit", "ATM Withdrawal", -200.00),
    ("debit", "Subscription - Streaming Service", -15.99),
    ("debit", "Fuel Station", -62.10),
    ("credit", "Refund - Online Purchase", 45.00),
    ("debit", "Restaurant Payment", -34.75),
    ("debit", "Mobile Phone Bill", -89.00),
    ("credit", "Transfer from Savings", 1_000.00),
    ("debit", "Online Transfer - Rent", -1_400.00),
    ("debit", "Pharmacy Purchase", -23.45),
    ("credit", "Federal Tax Refund", 820.00),
    ("debit", "Insurance Premium", -210.00),
]


def seed_data():
    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(User).count() > 0:
            return

        print("🌱 Seeding database with demo users and transactions...")

        for u_data in DEMO_USERS:
            # bcrypt has a hard limit of 72 bytes; truncate long values to avoid fatal errors
            raw_pwd = u_data["password"]
            pwd_bytes = raw_pwd.encode("utf-8")
            if len(pwd_bytes) > 72:
                print(f"⚠️  password for {u_data['username']} is {len(pwd_bytes)} bytes, truncating to 72")
                # cut bytes and decode back to string (ignore partial multibyte sequences)
                raw_pwd = pwd_bytes[:72].decode("utf-8", errors="ignore")

            try:
                hashed = hash_password(raw_pwd)
            except Exception as e:
                # if hashing still fails (should be rare thanks to auth.py fixes),
                # log it and fall back to a manual bcrypt call so seeding can continue.
                print(f"❌ error hashing password for {u_data['username']}: {e}")
                import bcrypt
                raw = raw_pwd.encode("utf-8")
                if len(raw) > 72:
                    raw = raw[:72]
                hashed = bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")
                print(f"⚠️  using manual bcrypt fallback for {u_data['username']}")

            user = User(
                username=u_data["username"],
                full_name=u_data["full_name"],
                email=u_data["email"],
                hashed_password=hashed,
                account_number=u_data["account_number"],
                balance=u_data["balance"],
                created_at=datetime.utcnow() - timedelta(days=365),
            )
            db.add(user)
            db.flush()  # get user.id

            # Seed 15 transactions spread over last 60 days
            templates = random.sample(TRANSACTION_TEMPLATES, 12)
            for i, (txn_type, desc, amount) in enumerate(templates):
                txn = Transaction(
                    user_id=user.id,
                    type=txn_type,
                    description=desc,
                    amount=amount,
                    timestamp=datetime.utcnow() - timedelta(days=random.randint(1, 60)),
                )
                db.add(txn)

        db.commit()
        print("✅ Seed complete.")
    except Exception as e:
        db.rollback()
        print(f"❌ Seed failed: {e}")
    finally:
        db.close()