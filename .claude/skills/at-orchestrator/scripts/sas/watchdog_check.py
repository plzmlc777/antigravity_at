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
import re
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
BACKUP_STALE_HOURS = int(os.environ.get("SAS_BACKUP_STALE_HOURS", "30"))
BACKUP_STATUS_FILE = Path.home() / ".ubuntu_backup_status"

NOW = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)

# Wrapper stdout includes "[sas-daily] log /abs/path/to/file.log" right after each
# script start — we mine that to read the actual error excerpt.
RUN_LOG_RE = re.compile(r"\[(?:sas|at)-[\w-]+\] log (\S+\.log)")

# Pattern → prescription. First match wins. Order matters: put more specific
# patterns before generic ones.
PRESCRIPTIONS = [
    {
        "category": "claude_path",
        "pattern": re.compile(r"claude: (?:command not found|명령어를 찾을 수 없음)", re.I),
        "suggestion": (
            "`claude` CLI not on PATH for the wrapper child shell.\n"
            "Verify wrapper has the npm-global export:\n"
            "  grep npm-global ~/auto_trading/.claude/skills/at-orchestrator/scripts/sas/sas_loop_wrapper.sh\n"
            "If the export line is missing, git pull and `pm2 restart all` on mint."
        ),
    },
    {
        "category": "claude_auth_expired",
        "pattern": re.compile(
            r"(Failed to authenticate.*?401|Invalid authentication credentials|authentication_error)",
            re.I,
        ),
        "suggestion": (
            "Claude Max-plan OAuth token expired or revoked.\n"
            "Re-auth interactively (browser OAuth flow):\n"
            "  ssh -t mint@183.99.228.81 'bash -lc claude'\n"
            "Type /login if not auto-prompted. Next cron fire works after success."
        ),
    },
    {
        "category": "db_unreachable",
        "pattern": re.compile(
            r"(psql:.*?(connection|connect to server).*?(refused|failed)|could not connect to server)",
            re.I,
        ),
        "suggestion": (
            "Postgres unreachable.\n"
            "  systemctl status postgresql --no-pager\n"
            "If down: sudo systemctl restart postgresql"
        ),
    },
    {
        "category": "disk_full",
        "pattern": re.compile(r"No space left on device", re.I),
        "suggestion": (
            "Disk full.\n"
            "  df -h\n"
            "  du -h --max-depth=1 ~ | sort -hr | head -10\n"
            "Likely culprits: ~/.pm2/logs, ~/db_backup_*.dump, runs/sas/*.log"
        ),
    },
    {
        "category": "python_module_missing",
        "pattern": re.compile(r"(ModuleNotFoundError|No module named ['\"]?[\w.]+['\"]?)", re.I),
        "suggestion": (
            "Python module missing — venv not activated or out of sync.\n"
            "  cd ~/auto_trading/backend && source venv/bin/activate && pip install -r requirements.txt"
        ),
    },
    {
        "category": "sqlalchemy_stale",
        "pattern": re.compile(r"StaleDataError|expected to update \d+ row|Multiple rows were found", re.I),
        "suggestion": (
            "SQLAlchemy identity-map conflict (session not refreshed).\n"
            "Daily generator already falls back to direct SQL update; verify backend logs."
        ),
    },
    {
        "category": "rate_limit",
        "pattern": re.compile(r"(rate.?limit|429 Too Many Requests|RateLimitError)", re.I),
        "suggestion": (
            "Upstream API rate limit (Claude/Binance/Kiwoom).\n"
            "Wait 5–15 min. If recurring, lower call frequency in the offending script."
        ),
    },
    {
        "category": "port_in_use",
        "pattern": re.compile(r"(address already in use|EADDRINUSE|port \d+ is already)", re.I),
        "suggestion": (
            "Port conflict.\n"
            "  lsof -i :8001\n"
            "Kill the stale process or restart the conflicting service."
        ),
    },
    {
        "category": "permission_denied",
        "pattern": re.compile(r"Permission denied", re.I),
        "suggestion": (
            "File or directory permission issue.\n"
            "Inspect the failing path's owner/mode. For runs/sas/* try: chmod 644 / chown mint:mint."
        ),
    },
    {
        "category": "git_conflict",
        "pattern": re.compile(r"(Merge conflict|CONFLICT \(content\)|needs merge|cannot pull)", re.I),
        "suggestion": (
            "Git pull blocked.\n"
            "  cd ~/auto_trading && git status\n"
            "Resolve conflict or `git stash` local changes, then pull."
        ),
    },
]


def find_recent_run_log(lines) -> str | None:
    """Return the most recent run-log path mentioned in wrapper stdout."""
    last = None
    for line in lines:
        m = RUN_LOG_RE.search(line)
        if m:
            last = m.group(1)
    return last


def extract_error_excerpt(run_log_path: str | None, max_lines: int = 15, max_chars: int = 1500) -> str | None:
    """Read the tail of an agent's run log for inclusion in the alert body."""
    if not run_log_path:
        return None
    p = Path(run_log_path)
    if not p.exists():
        return None
    try:
        text = p.read_text(errors="replace")
    except Exception:
        return None
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return None
    excerpt = "\n".join(lines[-max_lines:])
    if len(excerpt) > max_chars:
        excerpt = excerpt[-max_chars:]
    return excerpt


def match_prescription(text: str) -> dict | None:
    if not text:
        return None
    for p in PRESCRIPTIONS:
        if p["pattern"].search(text):
            return p
    return None


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


def check_backup_freshness() -> dict:
    """Confirm Ubuntu pull-mode backup is recent enough.

    The Ubuntu host runs sync_from_mint.sh on a daily cron (18:00 UTC).
    On success it scp's a status line back here. We check:
      - file exists
      - first field == 'OK'
      - timestamp within BACKUP_STALE_HOURS
    """
    if not BACKUP_STATUS_FILE.exists():
        return {
            "ok": False,
            "alert": {
                "tag": "backup_missing",
                "title": "Ubuntu backup status missing",
                "body": (
                    f"~/.ubuntu_backup_status not found on mint. Either the Ubuntu "
                    f"backup has never run, or the scp-back step failed. "
                    f"Check ubuntu cron and ~/db_backup/sync.log."
                ),
                "cooldown_hours": 24,
            },
        }
    try:
        line = BACKUP_STATUS_FILE.read_text().strip().splitlines()[0]
        parts = line.split("|")
        result, ts = parts[0], parts[1]
        last = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        delta_h = (NOW - last).total_seconds() / 3600
    except Exception as e:
        return {
            "ok": False,
            "alert": {
                "tag": "backup_status_corrupt",
                "title": "Ubuntu backup status unparseable",
                "body": f"Failed to parse ~/.ubuntu_backup_status: {e}",
                "cooldown_hours": 24,
            },
        }
    if result != "OK":
        return {
            "ok": False,
            "result": result,
            "delta_hours": round(delta_h, 1),
            "alert": {
                "tag": "backup_failed",
                "title": f"Ubuntu backup last result: {result}",
                "body": f"Last status line: {line}",
                "cooldown_hours": 24,
            },
        }
    if delta_h > BACKUP_STALE_HOURS:
        return {
            "ok": False,
            "delta_hours": round(delta_h, 1),
            "alert": {
                "tag": "backup_stale",
                "title": f"Ubuntu backup stale ({int(delta_h)}h)",
                "body": (
                    f"Last successful backup was {ts} ({int(delta_h)}h ago, "
                    f"threshold {BACKUP_STALE_HOURS}h). Ubuntu cron may have "
                    f"failed silently. Check: ssh ubuntu@172.30.1.60 "
                    f"'tail ~/db_backup/sync.log'"
                ),
                "cooldown_hours": 24,
            },
        }
    return {"ok": True, "delta_hours": round(delta_h, 1), "last": ts}


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
      [sas-loop] wrapper started for: <script>   (once per PM2 spawn)
      [sas-loop] executing: <script>
      ... (script output) ...
      [sas-loop] script exited with code N       (only on non-zero)
      [sas-loop] execution complete, scheduling next run...
      [sas-loop] next run: ...

    We only inspect lines after the most recent "wrapper started" so that
    pre-restart failures don't keep alerting forever after the bug is fixed.
    """
    out_log = PM2_LOG_DIR / f"{name}-out.log"
    if not out_log.exists():
        return {"ok": False, "reason": "log file missing"}
    try:
        all_lines = out_log.read_text(errors="replace").splitlines()
    except Exception as e:
        return {"ok": False, "reason": f"read error: {e}"}

    # Cut to the most recent wrapper boot — anything before that belongs to a
    # previous PM2 incarnation and is irrelevant for current health.
    boot_idx = -1
    for i, line in enumerate(all_lines):
        if "[sas-loop] wrapper started for:" in line:
            boot_idx = i
    tail = all_lines[boot_idx + 1:] if boot_idx >= 0 else all_lines[-200:]

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
                    "run_log_path": find_recent_run_log(window),
                }
    return {"ok": True, "status": "last_run_clean"}


def build_agent_alert(name: str, finding: dict) -> dict:
    excerpt = extract_error_excerpt(finding.get("run_log_path"))
    pres = match_prescription(excerpt or finding.get("line", ""))

    parts = [f"Wrapper: {finding['line']}"]
    if excerpt:
        parts.append(f"\nLast error excerpt:\n{excerpt}")
    if pres:
        parts.append(f"\n💡 Likely cause: {pres['category']}\n{pres['suggestion']}")
    else:
        parts.append("\n(no known prescription pattern matched — inspect the run log)")

    body = "\n".join(parts)
    if len(body) > 3500:  # Telegram hard limit ~4096; leave headroom for title.
        body = body[:3500] + "\n... (truncated)"

    return {
        "tag": f"agent_exit:{name}",
        "title": f"{name} exit={finding['exit_code']}",
        "body": body,
        "category": pres["category"] if pres else "unknown",
        "cooldown_hours": 12,
    }


def check_agent_exit_codes() -> dict:
    findings = {}
    alerts = []
    for name in SAS_AGENTS:
        result = parse_pm2_log(name)
        findings[name] = result
        if not result.get("ok") and "exit_code" in result:
            alerts.append(build_agent_alert(name, result))
    return {"per_agent": findings, "alerts": alerts}


def telegram_send(title: str, body: str) -> tuple[bool, str]:
    if not TG_TOKEN or not TG_CHAT:
        return False, "credentials missing"
    # No parse_mode — body contains shell snippets / paths that would break
    # Markdown escaping. Plain text is robust and Telegram still renders newlines.
    text = f"🚨 {title}\n\n{body}"
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TG_CHAT,
            "text": text,
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
    backup = check_backup_freshness()

    raised = []
    if audition.get("alert"):
        raised.append(audition["alert"])
    if backup.get("alert"):
        raised.append(backup["alert"])
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
        "checks": {"audition": audition, "backup": backup, "agents": agents},
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


def run_self_test() -> int:
    """Verify each known prescription pattern fires on a representative sample."""
    samples = [
        ("bash: claude: command not found", "claude_path"),
        ("claude: 명령어를 찾을 수 없음", "claude_path"),
        ("Failed to authenticate. API Error: 401 {...authentication_error...}", "claude_auth_expired"),
        ("psql: error: connection to server at localhost port 5432 failed: Connection refused", "db_unreachable"),
        ("OSError: [Errno 28] No space left on device", "disk_full"),
        ("ModuleNotFoundError: No module named 'pandas'", "python_module_missing"),
        ("sqlalchemy.orm.exc.StaleDataError: UPDATE statement on ...", "sqlalchemy_stale"),
        ("anthropic.RateLimitError: 429 Too Many Requests", "rate_limit"),
        ("OSError: [Errno 98] Address already in use", "port_in_use"),
        ("PermissionError: [Errno 13] Permission denied: '/etc/foo'", "permission_denied"),
        ("CONFLICT (content): Merge conflict in app/main.py", "git_conflict"),
        ("absolutely-never-seen-error xyz", None),
    ]
    print("Prescription self-test:")
    failures = 0
    for sample, expected in samples:
        m = match_prescription(sample)
        actual = m["category"] if m else None
        ok = actual == expected
        if not ok:
            failures += 1
        print(f"  [{'OK' if ok else 'FAIL'}] {sample[:60]:60s} -> {actual} (expected {expected})")
    if failures:
        print(f"\n{failures} failure(s).")
        return 1
    print("\nAll prescriptions matched expected categories.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-prescriptions":
        sys.exit(run_self_test())
    sys.exit(main())
