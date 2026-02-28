from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import time
import os

from database import init_db, save_session, get_sessions, get_stats, delete_session

# ── Discord notifier ─────────────────────────────────────────────────────────
DISCORD_LOGS_CHANNEL = "1476717294397952071"
OPENCLAW_URL = "http://localhost:9999"   # internal OpenClaw message API

NOTIFY_QUEUE = os.path.expanduser("~/.openclaw/worklog-notify.jsonl")

def notify_discord(message: str):
    """Write to notification queue — Neo picks this up on heartbeat and posts to Discord."""
    try:
        import json
        entry = json.dumps({"channel": DISCORD_LOGS_CHANNEL, "message": message, "ts": time.time()})
        with open(NOTIFY_QUEUE, "a") as f:
            f.write(entry + "\n")
    except Exception:
        pass  # silent — never break logging because of a notification failure


def should_notify(task_type: str, actual_hours: float, manual_estimate: float) -> bool:
    """Notify on scans, big tasks, or anything saving 10+ hours."""
    if task_type == "scan":
        return True
    if actual_hours >= 0.5:
        return True
    if manual_estimate and manual_estimate >= 10.0:
        return True
    return False


def build_notify_message(project: str, description: str, task_type: str,
                          actual_hours: float, manual_estimate: float) -> str:
    mins = round(actual_hours * 60, 1)
    time_str = f"{mins}m" if mins < 60 else f"{round(actual_hours, 1)}h"
    msg = f"📋 **WorkLog** · `{project}` · {description or task_type} · ⏱ {time_str}"
    if manual_estimate and manual_estimate > 0:
        multiplier = round(manual_estimate / actual_hours)
        msg += f" · **{multiplier}x faster than manual**"
    return msg

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY = "wl-justin-2026"  # hardcoded — change if needed

app = FastAPI(title="WorkLog API")


def require_key(x_wl_key: Optional[str] = Header(default=None)):
    if x_wl_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Models ───────────────────────────────────────────────────────────────────
class SessionIn(BaseModel):
    project: str
    description: Optional[str] = None
    task_type: Optional[str] = "manual"   # manual | timer | diagnosis | scan | agent
    actual_hours: float
    manual_estimate: Optional[float] = None
    timestamp: Optional[int] = None       # unix ms — defaults to now
    date: Optional[str] = None            # YYYY-MM-DD — defaults to today
    metadata: Optional[dict] = None


# ── Startup ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()


# ── API Routes ───────────────────────────────────────────────────────────────
@app.post("/api/log")
def log_session(session: SessionIn, x_wl_key: Optional[str] = Header(default=None)):
    require_key(x_wl_key)
    task_type = session.task_type or "manual"
    session_id = save_session(
        project=session.project,
        description=session.description,
        task_type=task_type,
        actual_hours=session.actual_hours,
        manual_estimate=session.manual_estimate,
        timestamp=session.timestamp,
        date=session.date,
        metadata=session.metadata,
    )
    # Notify Discord #logs for notable entries
    if should_notify(task_type, session.actual_hours, session.manual_estimate or 0):
        msg = build_notify_message(
            session.project,
            session.description or "",
            task_type,
            session.actual_hours,
            session.manual_estimate or 0,
        )
        notify_discord(msg)
    return {"ok": True, "id": session_id}


@app.get("/api/sessions")
def list_sessions(limit: int = 200, x_wl_key: Optional[str] = Header(default=None)):
    require_key(x_wl_key)
    return get_sessions(limit=limit)


@app.get("/api/stats")
def stats(x_wl_key: Optional[str] = Header(default=None)):
    require_key(x_wl_key)
    return get_stats()


@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: int, x_wl_key: Optional[str] = Header(default=None)):
    require_key(x_wl_key)
    delete_session(session_id)
    return {"ok": True}


# ── Static / SPA ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_index():
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8092)
