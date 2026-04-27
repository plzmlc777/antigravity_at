"""SAS pipeline health watchdog.

Detects silent failures (PM2 says online, but cycles are dying with non-zero
exit) and pipeline starvation (no new audition rows produced for too long),
then notifies via Telegram with per-tag cooldowns to suppress spam.

Reads credentials from environment (loaded by run_watchdog.sh from .env):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

Writes:
  runs/sas/status.json           -- latest health snapshot
  runs/sas/.alert_cooldowns.json -- per-tag last-sent timestamps
"""
import datetime
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[5]
RUNS_DIR = PROJECT_ROOT / ".claude" / "skills" / "at-orchestrator" / "runs" / "sas"
STATUS_FILE = RUNS_DIR / "status.json"
COOLDOWN_FILE = RUNS_DIR / ".alert_cooldowns.json"

PM2_LOG_DIR = Path.home() / ".pm2" / "logs"

SAS_AGENTS = [
    "sas-daily-generator",
    "sas-sandbox-processor",
    "sas-paper-scheduler",
    "sas-live-monitor",
    "sas-meta-observer",
    "sas-weekly-judge",
    "sas-monthly-resurrect",
    "at-weekly-cycle",
]

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
DAILY_STALE_HOURS = int(os.environ.get("SAS_DAILY_STALE_HOURS", "36"))

NOW = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def db_query(sql: str) -> str:
    env = {**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "antigravity_password")}
    res = subprocess.run(
        [
            "psql",
            "-U", os.environ.get("PGUSER", "antigravity_user"),
            "-h", os.environ.get("PGHOST", "localhost"),
            "-d", os.environ.get("PGDATABASE", "antigravity_db"),
            "-tAc", sql,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr.strip()}")
    return res.stdout.strip()


def check_audition_freshness() -> dict:
    """Latest audition created_at vs threshold."""
    try:
        latest_str = db_query("SELECT MAX(created_at) FROM strategy_audition;")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not latest_str:
        return {
            "ok": False,
            "alert": {
                "tag": "audition_empty",
                "title": "SAS audition table empty",
                "body": "strategy_audition has zero rows — pipeline never produced output.",
                "cooldown_hours": 24,
            },
        }
    latest = datetime.datetime.fromisoformat(latest_str).replace(tzinfo=datetime.timezone.utc)
    delta_h = (NOW - latest).total_seconds() / 3600
    out = {"ok": delta_h <= DAILY_STALE_HOURS, "delta_hours": round(delta_h, 1), "latest": latest_str}
    if not out["ok"]:
        out["alert"] = {
            "tag": "daily_stale",
            "title": f"SAS daily-generator stale ({int(delta_h)}h)",
            "body": (
                f"No new strategy_audition row since {latest_str} UTC "
                f"({int(delta_h)}h ago, threshold {DAILY_STALE_HOURS}h). "
                f"Daily generator may be failing silently."
            ),
            "cooldown_hours": 24,
        }
    return out


def parse_pm2_log(name: str) -> dict:
    """Inspect last cycle of an agent's pm2 stdout log.

    Wrapper writes:
      [sas-loop] executing: <script>
      ... (script output) ...
      [sas-loop] script exited with code N    (only on non-zero)
      [sas-loop] execution complete, scheduling next run...
      [sas-loop] next run: ...
    """
    out_log = PM2_LOG_DIR / f"{name}-out.log"
    if not out_log.exists():
        return {"ok": False, "reason": "log file missing"}
    try:
        tail = out_log.read_text(errors="replace").splitlines()[-200:]
    except Exception as e:
        return {"ok": False, "reason": f"read error: {e}"}

    # Find the most recent "executing:" line
    last_exec_idx = -1
    for i, line in enumerate(tail):
        if "[sas-loop] executing:" in line:
            last_exec_idx = i
    if last_exec_idx < 0:
        return {"ok": True, "status": "no_run_yet"}

    window = tail[last_exec_idx:]
    completed = any("execution complete" in l for l in window)
    if not completed:
        return {"ok": True, "status": "in_progress"}

    for line in window:
        if "[sas-loop] script exited with code" in line:
            try:
                code = int(line.rsplit("code", 1)[-1].strip())
            except Exception:
                code = -1
            if code != 0:
                return {
                    "ok": False,
                    "exit_code": code,
                    "line": line.strip(),
                }
    return {"ok": True, "status": "last_run_clean"}


def check_agent_exit_codes() -> dict:
    findings = {}
    alerts = []
    for name in SAS_AGENTS:
        result = parse_pm2_log(name)
        findings[name] = result
        if not result.get("ok") and "exit_code" in result:
            alerts.append({
                "tag": f"agent_exit:{name}",
                "title": f"{name} exit={result['exit_code']}",
                "body": f"Last cycle failed: {result.get('line', '(no detail)')}",
                "cooldown_hours": 12,
            })
    return {"per_agent": findings, "alerts": alerts}


def telegram_send(title: str, body: str) -> tuple[bool, str]:
    if not TG_TOKEN or not TG_CHAT:
        return False, "credentials missing"
    text = f"🚨 *{title}*\n```\n{body}\n```"
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TG_CHAT,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        }).encode()
        with urllib.request.urlopen(url, data=data, timeout=10) as r:
            return r.status == 200, f"http={r.status}"
    except Exception as e:
        return False, f"error: {e}"


def load_cooldowns() -> dict:
    if not COOLDOWN_FILE.exists():
        return {}
    try:
        return json.loads(COOLDOWN_FILE.read_text())
    except Exception:
        return {}


def main() -> int:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    audition = check_audition_freshness()
    agents = check_agent_exit_codes()

    raised = []
    if audition.get("alert"):
        raised.append(audition["alert"])
    raised.extend(agents.get("alerts", []))

    cooldowns = load_cooldowns()
    new_cooldowns = dict(cooldowns)
    sent, suppressed = [], []

    for alert in raised:
        tag = alert["tag"]
        cd = alert.get("cooldown_hours", 12)
        last = cooldowns.get(tag)
        if last:
            try:
                last_dt = datetime.datetime.fromisoformat(last)
                if (NOW - last_dt).total_seconds() < cd * 3600:
                    suppressed.append(tag)
                    continue
            except Exception:
                pass
        ok, info = telegram_send(alert["title"], alert["body"])
        if ok:
            new_cooldowns[tag] = NOW.isoformat()
            sent.append(tag)
        else:
            suppressed.append(f"{tag}(send_failed:{info})")

    COOLDOWN_FILE.write_text(json.dumps(new_cooldowns, indent=2))

    status = {
        "checked_at": NOW.isoformat(),
        "checks": {"audition": audition, "agents": agents},
        "alerts": {
            "raised": [a["tag"] for a in raised],
            "sent": sent,
            "suppressed": suppressed,
        },
        "telegram_configured": bool(TG_TOKEN and TG_CHAT),
    }
    STATUS_FILE.write_text(json.dumps(status, indent=2))
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
