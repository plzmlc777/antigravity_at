"""텔레그램 Q&A 봇 데몬 — 리포트 그룹에서 @멘션/답장 질문에 즉답.

2026-07-11 대표님 지시로 구축. 정책:
- 트리거: @coinAtsProject_bot 멘션 또는 봇 메시지에 대한 답장(reply)만.
  (봇 privacy mode OFF 상태라 잡담이 전부 수신됨 → 코드 필터 필수)
- 답변 대상: 등록 그룹의 참가자 전원. 미등록 chat(DM 포함)은 무시.
- 보안: 조회 전용. headless claude에 파일/셸/웹 도구 전면 차단
  (--disallowedTools + no bypass) → 사전 수집된 컨텍스트로만 답변.
  그룹 참가자의 prompt injection이 있어도 시스템 접근 경로가 없음.
- 사용량 가드: chat당 6건/h, 전역 20건/h, 최소 10초 간격.

Run: PYTHONPATH=. python3 scripts/telegram/qa_bot.py  (PM2: telegram-qa-bot)
Config: configs/telegram_qa_bot.json
"""
import json
import logging
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tg_qa")

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BACKEND, "configs", "telegram_qa_bot.json")
STATE_DIR = os.path.join(BACKEND, "runs", "telegram_qa")
STATE_PATH = os.path.join(STATE_DIR, "state.json")
SANDBOX = "/tmp/tg_qa_sandbox"
CLAUDE_BIN = os.path.expanduser("~/.npm-global/bin/claude")
TOKEN_ENV_FILE = os.path.expanduser("~/.claude/oauth_token.env")
DISALLOWED_TOOLS = ("Bash,Read,Write,Edit,MultiEdit,NotebookEdit,Glob,Grep,LS,"
                    "WebFetch,WebSearch,Task,Agent,TodoWrite,KillShell,BashOutput")
MAX_ANSWER_CHARS = 3500
MAX_QUESTION_CHARS = 1500


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"offset": 0}


def save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)


def bot_token(account_id: int) -> str:
    sys.path.insert(0, BACKEND)
    from app.db.session import SessionLocal
    from app.models.user import User  # noqa: F401 — resolves mapper
    from app.models.account import ExchangeAccount
    from app.core import security
    db = SessionLocal()
    try:
        acc = db.query(ExchangeAccount).get(account_id)
        return security.decrypt_key(acc.encrypted_telegram_bot_token)
    finally:
        db.close()


def tg_api(token: str, method: str, params: dict, timeout: int = 60):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=data, timeout=timeout) as r:
        return json.load(r)


def claude_env() -> dict:
    env = {**os.environ}
    try:
        for line in open(TOKEN_ENV_FILE):
            line = line.strip()
            if line.startswith("export CLAUDE_CODE_OAUTH_TOKEN="):
                env["CLAUDE_CODE_OAUTH_TOKEN"] = line.split("=", 1)[1]
    except Exception:
        pass
    return env


# ── 그룹별 컨텍스트 빌더 (SELECT/파일 읽기 전용, 실패해도 답변은 진행) ──

def _ctx_binance() -> str:
    parts = []
    try:
        st = json.load(open(os.path.join(BACKEND, "runs", "tier_governor", "state.json")))
        seats = st.get("seats", {})
        parts.append(f"[2군 리그] 좌석 {seats.get('used')}/{seats.get('max')}, 승격 큐 {seats.get('queue')}")
        rounds = st.get("league", {}).get("rounds", [])[-1:]
        if rounds:
            parts.append(f"[최근 리그 라운드] {json.dumps(rounds[0], ensure_ascii=False)[:400]}")
    except Exception as exc:
        log.warning("ctx tier state failed: %s", exc)
    try:
        sys.path.insert(0, BACKEND)
        from sqlalchemy import text
        from app.db.session import engine
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT e.symbol, count(*), round(sum(e.realized_pnl)::numeric,2)
                FROM live_trade_executions e JOIN live_bot_sessions s ON s.id=e.session_id
                WHERE s.account_id=8 AND e.is_paper=false AND e.status='FILLED'
                  AND e.order_filled_at > now() - interval '14 days'
                GROUP BY 1 ORDER BY 3 DESC LIMIT 10"""))
            t = ", ".join(f"{r[0]} {r[1]}건 {r[2]:+}USDT" for r in rows)
            if t:
                parts.append(f"[1군 신상저격수 최근 14일 실현손익] {t}")
            rows = conn.execute(text("""
                SELECT symbol, status FROM live_bot_sessions
                WHERE account_id=8 AND is_paper=false AND status='RUNNING'"""))
            syms = ", ".join(r[0] for r in rows)
            parts.append(f"[1군 러닝 세션] {syms}")
    except Exception as exc:
        log.warning("ctx db failed: %s", exc)
    try:
        import glob
        rows = []
        for sdir in glob.glob(os.path.join(BACKEND, "runs", "paper_sessions", "*")):
            sj = os.path.join(sdir, "session.json")
            if not os.path.exists(sj):
                continue
            m = json.load(open(sj))
            if m.get("status") != "active" or "lifecycle" in m["name"] or m["symbol"].isdigit():
                continue
            eqp = os.path.join(sdir, "equity.jsonl")
            last = None
            with open(eqp) as f:
                for line in f:
                    if line.strip():
                        last = line
            eq = json.loads(last)["equity"] if last else None
            rows.append((m["name"], eq))
        rows.sort(key=lambda r: -(r[1] or 0))
        parts.append("[2군 24석 equity 상위] " + ", ".join(f"{n.split('_paper_seed')[0]}={e:,.0f}" for n, e in rows[:8]))
    except Exception as exc:
        log.warning("ctx league failed: %s", exc)
    return "\n".join(parts)


CTX_BUILDERS = {"binance": _ctx_binance}


def build_answer(cfg: dict, group: dict, question: str, reply_text: str) -> str:
    ctx = ""
    builder = group.get("context_builder")
    if builder and builder in CTX_BUILDERS:
        try:
            ctx = CTX_BUILDERS[builder]()
        except Exception as exc:
            log.warning("context builder failed: %s", exc)
    prompt = f"""당신은 Antigravity 자동매매 시스템의 텔레그램 Q&A 봇 'AUTO BOT'입니다.
그룹 참가자의 질문에 아래 정보만으로 답변하세요.

[그룹 주제]
{group.get('profile', '')}

[실시간 시스템 컨텍스트]
{ctx or '(없음)'}

[질문이 답장으로 달린 리포트 원문]
{reply_text[:2000] if reply_text else '(없음)'}

[질문]
{question[:MAX_QUESTION_CHARS]}

규칙:
- 한국어로 간결하게 (800자 이내), 텔레그램 평문 (마크다운/HTML 금지).
- 제공된 컨텍스트에 없는 수치는 추측하지 말고 "해당 데이터는 지금 조회할 수 없다"고 답할 것.
- 매매 실행/설정 변경/개인정보/시스템 내부 자격증명 요청은 정중히 거절: 당신은 조회 전용 봇.
- 질문이 그룹 주제와 무관하면 짧게 주제 범위를 안내."""
    os.makedirs(SANDBOX, exist_ok=True)
    r = subprocess.run(
        [CLAUDE_BIN, "-p", prompt,
         "--model", cfg.get("answer_model", "sonnet"),
         "--disallowedTools", DISALLOWED_TOOLS],
        cwd=SANDBOX, env=claude_env(),
        capture_output=True, text=True, timeout=150)
    ans = (r.stdout or "").strip()
    if not ans:
        log.error("claude empty answer rc=%s err=%s", r.returncode, (r.stderr or "")[-300:])
        return "지금은 답변 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."
    return ans[:MAX_ANSWER_CHARS]


class RateLimiter:
    def __init__(self, cfg: dict):
        rl = cfg.get("rate_limit", {})
        self.per_chat = rl.get("per_chat_per_hour", 6)
        self.global_h = rl.get("global_per_hour", 20)
        self.min_gap = rl.get("min_gap_seconds", 10)
        self.chat_hits: dict[str, deque] = {}
        self.global_hits: deque = deque()
        self.last_ts = 0.0

    def allow(self, chat_id: str) -> bool:
        now = time.time()
        hour_ago = now - 3600
        self.global_hits = deque(t for t in self.global_hits if t > hour_ago)
        hits = self.chat_hits.setdefault(chat_id, deque())
        while hits and hits[0] <= hour_ago:
            hits.popleft()
        if now - self.last_ts < self.min_gap:
            return False
        if len(hits) >= self.per_chat or len(self.global_hits) >= self.global_h:
            return False
        hits.append(now)
        self.global_hits.append(now)
        self.last_ts = now
        return True


def is_addressed(msg: dict, bot_username: str, bot_id: int) -> bool:
    text = msg.get("text", "") or ""
    mention = f"@{bot_username}".lower()
    if mention in text.lower():
        return True
    rt = msg.get("reply_to_message")
    if rt and rt.get("from", {}).get("id") == bot_id:
        return True
    return False


def main():
    cfg = load_config()
    token = bot_token(cfg.get("bot_account_id", 8))
    me = tg_api(token, "getMe", {})["result"]
    bot_username, bot_id = me["username"], me["id"]
    log.info("bot @%s (%s) online — groups: %s", bot_username, me.get("first_name"),
             list(cfg["groups"].keys()))
    state = load_state()
    limiter = RateLimiter(cfg)
    started = time.time()

    while True:
        try:
            resp = tg_api(token, "getUpdates",
                          {"offset": state.get("offset", 0) + 1, "timeout": 50,
                           "allowed_updates": json.dumps(["message"])}, timeout=70)
            for upd in resp.get("result", []):
                state["offset"] = max(state.get("offset", 0), upd["update_id"])
                msg = upd.get("message") or {}
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id not in cfg["groups"]:
                    continue
                if not msg.get("text"):
                    continue
                # 봇 기동 이전 메시지 재생 방지 (5분 유예)
                if msg.get("date", 0) < started - 300:
                    continue
                if not is_addressed(msg, bot_username, bot_id):
                    continue
                if not limiter.allow(chat_id):
                    log.info("rate-limited chat %s", chat_id)
                    continue
                q = msg["text"].replace(f"@{bot_username}", "").strip()
                rt = msg.get("reply_to_message") or {}
                reply_text = rt.get("text", "") if rt.get("from", {}).get("id") == bot_id else ""
                who = msg.get("from", {}).get("first_name", "?")
                log.info("Q from %s in %s: %s", who, cfg["groups"][chat_id]["name"], q[:120])
                save_state(state)
                try:
                    ans = build_answer(cfg, cfg["groups"][chat_id], q, reply_text)
                except subprocess.TimeoutExpired:
                    ans = "답변 생성이 시간 초과됐습니다. 질문을 조금 더 구체적으로 다시 물어봐 주세요."
                except Exception as exc:
                    log.error("answer failed: %s", exc)
                    ans = "답변 생성 중 오류가 발생했습니다."
                send_resp = tg_api(token, "sendMessage",
                       {"chat_id": chat_id, "text": ans,
                        "reply_to_message_id": msg.get("message_id", ""),
                        "disable_web_page_preview": "true"}, timeout=30)
                log.info("answered in %s (%d chars)", cfg["groups"][chat_id]["name"], len(ans))
                try:
                    from app.core.telegram_sent_log import record_sent, extract_message_id
                    record_sent(chat_id, extract_message_id(send_resp), ans, source="qa_bot")
                except Exception:
                    pass
            save_state(state)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            log.error("poll loop error: %s", exc)
            time.sleep(10)


if __name__ == "__main__":
    main()
