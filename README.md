# 🏛️ Cerberus National Bank — Experimental Defense System

A Docker-based banking simulation built to demonstrate and eventually integrate the **Cerberus AI Defense System** — a three-layer phishing and credential theft prevention architecture.

---

## 🚀 Quick Start

```bash
# Clone / enter the project directory
cd cerberus-banking

# Build and launch all containers
docker compose up --build

# App is live at:
# → http://localhost:8000
```

---

## 🧪 Demo Credentials

| Username | Password           | Balance        |
|----------|--------------------|----------------|
| jsmith   | Password123!       | $24,850.75     |
| agarcia  | SecurePass99!      | $8,340.20      |
| admin    | Admin@CerberusBank1| $1,250,000.00  |

> **Try wrong credentials** to trigger the Cerberus intercept → decoy honeypot flow.

---

## 🔴 Cerberus Integration Point

The critical hook is in `backend/main.py`:

```
POST /login
    │
    ├── ✅ Correct password ──────────────────────────► /dashboard
    │
    └── ❌ Wrong password ──► /cerberus/intercept ──► /decoy
                                      │
                                      └─ THIS IS WHERE YOU PLUG IN:
                                           Layer 1: Decoy Engine
                                           Layer 2: Credential Sentinel
                                           Layer 3: BEC Assassin
```

**File:** `backend/main.py` → `@app.get("/cerberus/intercept")`

All failed login attempts are stored in the `login_attempts` table with:
- `username`, `ip_address`, `user_agent`, `timestamp`
- `flagged_by_cerberus` (bool) — set this to `True` when Cerberus flags an attempt
- `cerberus_notes` (text) — free-form Cerberus analysis output

---

## 📡 API Endpoints

| Method | Path                   | Description                          |
|--------|------------------------|--------------------------------------|
| GET    | `/login`               | Login page                           |
| POST   | `/login`               | Authenticate user                    |
| GET    | `/cerberus/intercept`  | 🔴 CERBERUS HOOK — failed logins     |
| GET    | `/decoy`               | Honeypot decoy page                  |
| GET    | `/dashboard`           | Banking dashboard (auth required)    |
| POST   | `/transfer`            | Mock fund transfer (auth required)   |
| GET    | `/logout`              | End session                          |
| GET    | `/cerberus/status`     | JSON health/stats endpoint           |

---

## 🗄️ Database Schema

**SQLite** — persisted in Docker volume `cerberus-banking-db`

```
users              login_attempts         transactions
─────────────      ──────────────────     ─────────────────
id                 id                     id
username           username               user_id
full_name          user_id (FK)           type (credit/debit)
email              ip_address             description
hashed_password    user_agent             amount
account_number     success                timestamp
balance            timestamp
created_at         flagged_by_cerberus  ← Cerberus sets this
                   cerberus_notes       ← Cerberus writes here
```

---

## 🐺 Future Cerberus Services (docker-compose.yml)

Stubs are already in `docker-compose.yml` — just uncomment to add:

```yaml
cerberus-decoy:     port 8001   # Decoy Engine microservice
cerberus-sentinel:  port 8002   # Credential Sentinel microservice
cerberus-bec:       port 8003   # BEC Assassin microservice
```

All services share the `cerberus-network` Docker bridge network, so they can communicate internally by service name.

---

## 🛑 Stopping

```bash
docker compose down           # stop containers
docker compose down -v        # stop + wipe database
```
