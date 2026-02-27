from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import HTTPException
from database import init_db, SessionLocal
from models import User, LoginAttempt, Transaction
from auth import verify_password, create_session, get_current_user, destroy_session
from seed import seed_data
from datetime import datetime
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cerberus-bank")

app = FastAPI(title="Cerberus Banking System")

# Use absolute path so it works regardless of working directory
# templates folder may live alongside this file or in the parent directory (depends on how the project
# is laid out during development vs. container build).  Try backend/templates first, then fall back.
base_dir = os.path.dirname(os.path.abspath(__file__))
candidate = os.path.join(base_dir, "templates")
if not os.path.isdir(candidate):
    # fallback to parent (useful when templates were moved outside backend)
    candidate = os.path.abspath(os.path.join(base_dir, "..", "templates"))
TEMPLATES_DIR = candidate

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def render_template(name: str, context: dict, status_code: int = 200):
    """Wrapper around Jinja2Templates.TemplateResponse that recovers from
    missing files to avoid crashing during development/mounting races.
    """
    try:
        return templates.TemplateResponse(name, context, status_code=status_code)
    except Exception as exc:
        # log the full exception so we can diagnose path issues without a 500 stacktrace
        logger.error("template render failed for %s: %s", name, exc)
        # fall back to a simple error page
        return HTMLResponse(
            f"<h1>Template error</h1><pre>{exc}</pre>", status_code=500
        )



# ─────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    init_db()
    seed_data()
    # sanity check template files early so any mounting or path issues are
    # logged before a user hits the page.
    for fname in ("login.html", "dashboard.html", "decoy.html"):
        p = os.path.join(TEMPLATES_DIR, fname)
        if not os.path.isfile(p):
            logger.error("missing template during startup: %s", p)
    logger.info("🏦 Cerberus Banking System online")


# ─────────────────────────────────────────────
#  ROOT
# ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/login")


# ─────────────────────────────────────────────
#  LOGIN
# ─────────────────────────────────────────────
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # If already logged in, go straight to dashboard
    token = request.cookies.get("session_token")
    if get_current_user(token):
        return RedirectResponse("/dashboard")
    return render_template("login.html", {"request": request})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    # 1. Verify that request came from Cerberus proxy (only POST needs it)
    header = request.headers.get("X-Cerberus-Proxy")
    expected = os.getenv("PROXY_SECRET_KEY")
    logger.info(f"Received proxy header: '{header}', expected: '{expected}'")
    if header != expected:
        raise HTTPException(status_code=403, detail="Forbidden")

    db = SessionLocal()
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")
    
    attempt = LoginAttempt(
        username=username,
        ip_address=client_ip,
        user_agent=user_agent,
        timestamp=datetime.utcnow(),
        success=False,
    )

    user = db.query(User).filter(User.username == username).first()

    if user and verify_password(password, user.hashed_password):
        # ── SUCCESSFUL LOGIN ──────────────────
        attempt.success = True
        attempt.user_id = user.id
        db.add(attempt)
        db.commit()
        db.refresh(user)

        # Detach user from DB session before storing in memory
        db.expunge(user)

        token = create_session(user)

        # Fetch recent transactions
        transactions = (
            db.query(Transaction)
            .filter(Transaction.user_id == user.id)
            .order_by(Transaction.timestamp.desc())
            .limit(10)
            .all()
        )
        txn_data = [
            {
                "type": t.type,
                "description": t.description,
                "amount": t.amount,
                "timestamp": t.timestamp,
            }
            for t in transactions
        ]
        db.close()

        hour = datetime.utcnow().hour
        greeting = "Morning" if hour < 12 else "Afternoon" if hour < 17 else "Evening"

        logger.info(f"✅ LOGIN SUCCESS | user={username} | ip={client_ip}")

        # Render dashboard directly (no redirect)
        response = render_template(
            "dashboard.html",
            {"request": request, "user": user, "transactions": txn_data, "greeting": greeting}
        )
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            samesite="lax",
        )
        return response

    else:
        # ── FAILED LOGIN ──────────────────────
        attempt.success = False
        if user:
            attempt.user_id = user.id
        db.add(attempt)
        db.commit()
        db.close()

        logger.warning(f"🚨 LOGIN FAILED  | user={username} | ip={client_ip}")

        # Return a normal 401 error – Cerberus will forward this to the client.
        # (High‑risk attempts are already trapped before reaching this point.)
        raise HTTPException(status_code=401, detail="Invalid credentials")
async def cerberus_intercept(
    request: Request,
    username: str = "",
    ip: str = "",
):
    """
    ╔══════════════════════════════════════════════════════════╗
    ║           🔴  CERBERUS INTEGRATION POINT                ║
    ║                                                          ║
    ║  Every failed login flows through this endpoint.        ║
    ║  This is where the three Cerberus layers hook in:       ║
    ║                                                          ║
    ║  Layer 1 ─ Decoy Engine                                 ║
    ║    → Spin up isolated fake session for this user        ║
    ║    → Serve convincing decoy banking environment          ║
    ║    → Track attacker behavior + collect intelligence      ║
    ║                                                          ║
    ║  Layer 2 ─ Credential Sentinel                          ║
    ║    → Query LoginAttempt table for brute-force patterns   ║
    ║    → Analyze behavioral biometrics (keystroke timing)    ║
    ║    → Flag or block IPs exceeding threshold               ║
    ║                                                          ║
    ║  Layer 3 ─ BEC Assassin                                 ║
    ║    → Cross-reference username against email patterns     ║
    ║    → Flag if part of a known BEC campaign                ║
    ║                                                          ║
    ║  For now: redirects to /decoy (honeypot placeholder)    ║
    ╚══════════════════════════════════════════════════════════╝
    """

    # ── Future Cerberus logic replaces the block below ────────
    cerberus_payload = {
        "username": username,
        "ip": ip,
        "timestamp": datetime.utcnow().isoformat(),
        "action": "decoy_redirect",     # future: "block" | "honeypot" | "alert"
        "layer_triggered": "decoy_engine",
    }
    logger.info(f"🐺 CERBERUS INTERCEPT | payload={cerberus_payload}")
    # ──────────────────────────────────────────────────────────

    return RedirectResponse("/decoy", status_code=302)

@app.post("/proxy/login", response_class=HTMLResponse)
async def proxy_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Proxy-protected login endpoint. Validates a shared secret header
    then delegates to the normal login handler logic.
    """
    header = request.headers.get("X-Cerberus-Proxy")
    if header != os.getenv("PROXY_SECRET_KEY"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # delegate to existing login handler logic
    return await login_submit(request, username=username, password=password)

# ─────────────────────────────────────────────
#  DECOY PAGE (Cerberus Honeypot)
# ─────────────────────────────────────────────
@app.get("/decoy", response_class=HTMLResponse)
async def decoy_page(request: Request):
    return render_template("decoy.html", {"request": request})


# ─────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    token = request.cookies.get("session_token")
    user = get_current_user(token)
    if not user:
        return RedirectResponse("/login")

    db = SessionLocal()
    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.timestamp.desc())
        .limit(10)
        .all()
    )
    # Detach for template rendering
    txn_data = [
        {
            "type": t.type,
            "description": t.description,
            "amount": t.amount,
            "timestamp": t.timestamp,
        }
        for t in transactions
    ]
    db.close()

    hour = datetime.utcnow().hour
    greeting = "Morning" if hour < 12 else "Afternoon" if hour < 17 else "Evening"

    return render_template(
        "dashboard.html",
        {"request": request, "user": user, "transactions": txn_data, "greeting": greeting},
    )


# ─────────────────────────────────────────────
#  TRANSFER (Mock)
# ─────────────────────────────────────────────
@app.post("/transfer")
async def transfer(
    request: Request,
    recipient_account: str = Form(...),
    amount: float = Form(...),
    memo: str = Form(""),
):
    token = request.cookies.get("session_token")
    user = get_current_user(token)
    if not user:
        return RedirectResponse("/login", status_code=302)

    db = SessionLocal()
    db_user = db.query(User).filter(User.id == user.id).first()

    if db_user and db_user.balance >= amount > 0:
        db_user.balance -= amount
        txn = Transaction(
            user_id=db_user.id,
            type="debit",
            description=f"Transfer to {recipient_account}" + (f" — {memo}" if memo else ""),
            amount=-amount,
            timestamp=datetime.utcnow(),
        )
        db.add(txn)
        db.commit()

        # Update in-memory session user balance
        user.balance = db_user.balance
        logger.info(f"💸 TRANSFER | user={user.username} | amount=${amount:.2f} | to={recipient_account}")

    db.close()
    return RedirectResponse("/dashboard", status_code=302)


# ─────────────────────────────────────────────
#  LOGOUT
# ─────────────────────────────────────────────
@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        destroy_session(token)
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session_token")
    return response


# ─────────────────────────────────────────────
#  CERBERUS STATUS API (future monitoring endpoint)
# ─────────────────────────────────────────────
@app.get("/cerberus/status")
async def cerberus_status():
    """Health/status endpoint for Cerberus monitoring integration."""
    db = SessionLocal()
    total_attempts = db.query(LoginAttempt).count()
    failed_attempts = db.query(LoginAttempt).filter(LoginAttempt.success == False).count()
    db.close()
    return {
        "status": "active",
        "system": "Cerberus Defense Layer",
        "layers": {
            "decoy_engine": "ready",
            "credential_sentinel": "ready",
            "bec_assassin": "ready",
        },
        "stats": {
            "total_login_attempts": total_attempts,
            "failed_attempts": failed_attempts,
            "interceptions": failed_attempts,
        },
    }
