"""
AI Analysis Scheduler Service

Background scheduler that periodically runs Claude CLI trading-analyst agent
on live trading sessions based on user-configured schedules.
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import SessionLocal

logger = logging.getLogger("AnalysisScheduler")

# KST offset (UTC+9)
KST_OFFSET = timedelta(hours=9)


class AnalysisScheduler:
    def __init__(self):
        self.is_running = False
        self._task = None

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("AnalysisScheduler started")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AnalysisScheduler stopped")

    async def _scheduler_loop(self):
        """Main loop: check every 60 seconds for due schedules."""
        while self.is_running:
            try:
                await self._check_due_schedules()
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)

            await asyncio.sleep(60)

    async def _check_due_schedules(self):
        """Find and execute due schedules."""
        db: Session = SessionLocal()
        try:
            now_utc = datetime.utcnow()

            # Find enabled schedules that are due
            rows = db.execute(text("""
                SELECT id, user_id, account_id, schedule_type, schedule_time,
                       schedule_day, target_sessions, next_run_at
                FROM ai_analysis_schedules
                WHERE enabled = TRUE AND next_run_at IS NOT NULL AND next_run_at <= :now
            """), {"now": now_utc}).fetchall()

            if not rows:
                return

            for row in rows:
                schedule_id = row[0]
                user_id = row[1]
                account_id = row[2]
                schedule_type = row[3]
                schedule_time = row[4]
                schedule_day = row[5]
                target_sessions = row[6]
                next_run_at = row[7]

                logger.info(f"Running scheduled analysis: schedule={schedule_id}, user={user_id}")

                try:
                    await self._run_schedule(db, schedule_id, user_id, account_id, target_sessions)
                except Exception as e:
                    logger.error(f"Schedule {schedule_id} failed: {e}", exc_info=True)

                # Update last_run_at and compute next_run_at
                new_next = self._compute_next_run(schedule_type, schedule_time, schedule_day)
                db.execute(text("""
                    UPDATE ai_analysis_schedules
                    SET last_run_at = :now, next_run_at = :next_run, updated_at = :now
                    WHERE id = :sid
                """), {"now": now_utc, "next_run": new_next, "sid": schedule_id})
                db.commit()

        except Exception as e:
            logger.error(f"Error checking schedules: {e}", exc_info=True)
        finally:
            db.close()

    async def _run_schedule(self, db: Session, schedule_id: str, user_id: int, account_id: Optional[int], target_sessions):
        """Execute analysis for all target sessions of a schedule."""
        # Resolve target sessions
        sessions = self._resolve_target_sessions(db, target_sessions, user_id, account_id)

        if not sessions:
            logger.warning(f"No active sessions found for schedule {schedule_id}")
            return

        for session_info in sessions:
            try:
                await self._analyze_session(db, schedule_id, user_id, session_info)
            except Exception as e:
                logger.error(f"Analysis failed for session {session_info['id']}: {e}", exc_info=True)

    def _resolve_target_sessions(self, db: Session, target_sessions, user_id: int, account_id: Optional[int]) -> List[Dict]:
        """Resolve target session IDs to actual session info."""
        if not target_sessions:
            target_sessions = ["all_running"]

        if isinstance(target_sessions, str):
            try:
                target_sessions = json.loads(target_sessions)
            except (json.JSONDecodeError, TypeError):
                target_sessions = [target_sessions]

        if "all_running" in target_sessions:
            # Get all running sessions for this user/account
            query = """
                SELECT s.id, s.symbol, s.strategy_name, s.strategy_config, s.is_paper, s.account_id
                FROM live_bot_sessions s
                WHERE s.status = 'RUNNING'
            """
            params = {}

            if account_id:
                query += " AND s.account_id = :account_id"
                params["account_id"] = account_id

            rows = db.execute(text(query), params).fetchall()
        else:
            # Get specific sessions
            placeholders = ", ".join([f":s{i}" for i in range(len(target_sessions))])
            params = {f"s{i}": sid for i, sid in enumerate(target_sessions)}
            rows = db.execute(text(f"""
                SELECT id, symbol, strategy_name, strategy_config, is_paper, account_id
                FROM live_bot_sessions
                WHERE id IN ({placeholders}) AND status = 'RUNNING'
            """), params).fetchall()

        return [
            {
                "id": r[0], "symbol": r[1], "strategy_name": r[2],
                "strategy_config": r[3], "is_paper": r[4], "account_id": r[5]
            }
            for r in rows
        ]

    async def _analyze_session(self, db: Session, schedule_id: str, user_id: int, session_info: Dict):
        """Run full analysis pipeline for a single session."""
        from .live_ai_evaluation import LiveAIEvaluationService
        from .telegram_service import TelegramNotificationService
        from ..models.analysis_report import AIAnalysisReport
        from ..models.live_trading import generate_uuid

        session_id = session_info["id"]
        symbol = session_info["symbol"]
        strategy_name = session_info["strategy_name"]
        strategy_config = session_info["strategy_config"] or {}
        is_paper = session_info["is_paper"]

        # Check for duplicate running analysis
        existing = db.execute(text("""
            SELECT id FROM ai_analysis_reports
            WHERE session_id = :sid AND status = 'running'
        """), {"sid": session_id}).fetchone()

        if existing:
            logger.info(f"Analysis already running for session {session_id}, skipping")
            return

        # Create report record
        report_id = generate_uuid()
        db.execute(text("""
            INSERT INTO ai_analysis_reports
                (id, schedule_id, user_id, session_id, symbol, strategy_name,
                 report_type, status, strategy_config, created_at)
            VALUES
                (:id, :schedule_id, :user_id, :session_id, :symbol, :strategy_name,
                 'scheduled', 'running', :config, :now)
        """), {
            "id": report_id, "schedule_id": schedule_id, "user_id": user_id,
            "session_id": session_id, "symbol": symbol, "strategy_name": strategy_name,
            "config": json.dumps(strategy_config), "now": datetime.utcnow()
        })
        db.commit()

        try:
            # Step 1: Collect data using LiveAIEvaluationService
            eval_service = LiveAIEvaluationService(db, user_id=user_id)

            live_stats = eval_service.collect_live_stats(session_id, symbol, n_cycles=10, is_paper=is_paper)
            if "error" in live_stats:
                raise Exception(f"Live stats error: {live_stats['error']}")

            backtest_stats = await eval_service.run_backtest_for_comparison(
                symbol, strategy_name, strategy_config, days=30
            )
            comparison = eval_service.compute_comparison(live_stats, backtest_stats)

            # Step 2: Build context for Claude agent
            context_data = {
                "session_info": {
                    "session_id": session_id,
                    "symbol": symbol,
                    "strategy_name": strategy_name,
                    "is_paper": is_paper,
                },
                "strategy_config": strategy_config,
                "trade_summary": live_stats,
                "backtest_comparison": comparison,
                "backtest_stats": backtest_stats,
            }

            # Step 3: Call Claude CLI agent
            ai_result = await self._call_claude_agent(context_data, symbol, strategy_name)

            # Step 4: Parse and save results
            grade = ai_result.get("grade")
            recommendations = ai_result.get("recommendations", [])
            news_data = ai_result.get("news_articles", [])
            risk_level = ai_result.get("risk_level")
            action = ai_result.get("action")
            ai_analysis_text = json.dumps(ai_result, ensure_ascii=False)

            db.execute(text("""
                UPDATE ai_analysis_reports SET
                    status = 'completed',
                    trade_summary = :trade_summary,
                    backtest_comparison = :comparison,
                    ai_analysis = :ai_analysis,
                    ai_model = :ai_model,
                    news_data = :news_data,
                    grade = :grade,
                    key_findings = :key_findings,
                    recommendations = :recommendations,
                    risk_level = :risk_level,
                    action = :action,
                    completed_at = :now
                WHERE id = :rid
            """), {
                "trade_summary": json.dumps(live_stats),
                "comparison": json.dumps(comparison),
                "ai_analysis": ai_analysis_text,
                "ai_model": "claude-sonnet",
                "news_data": json.dumps(news_data),
                "grade": grade,
                "key_findings": json.dumps({"summary": ai_result.get("summary"), "performance_analysis": ai_result.get("performance_analysis")}),
                "recommendations": json.dumps(recommendations),
                "risk_level": risk_level,
                "action": action,
                "now": datetime.utcnow(),
                "rid": report_id,
            })
            db.commit()

            # Step 5: Send Telegram notification
            try:
                telegram = TelegramNotificationService(db, user_id=user_id)
                await self._send_telegram_report(telegram, symbol, strategy_name, ai_result, is_paper)

                db.execute(text("""
                    UPDATE ai_analysis_reports SET telegram_sent = TRUE WHERE id = :rid
                """), {"rid": report_id})
                db.commit()
            except Exception as e:
                logger.error(f"Telegram notification failed: {e}")

            logger.info(f"Analysis completed: session={session_id}, grade={grade}")

        except Exception as e:
            logger.error(f"Analysis pipeline failed for session {session_id}: {e}", exc_info=True)
            db.execute(text("""
                UPDATE ai_analysis_reports SET
                    status = 'failed', error_message = :err, completed_at = :now
                WHERE id = :rid
            """), {"err": str(e)[:500], "now": datetime.utcnow(), "rid": report_id})
            db.commit()

    async def _call_claude_agent(self, context_data: Dict, symbol: str, strategy_name: str) -> Dict:
        """Call Claude CLI with trading-analyst agent."""
        claude_path = shutil.which("claude")
        if not claude_path:
            raise Exception("Claude CLI not found")

        # Write context to temp file
        tmp_file = None
        try:
            tmp_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', prefix='analysis_ctx_',
                dir='/tmp', delete=False
            )
            json.dump(context_data, tmp_file, ensure_ascii=False, indent=2)
            tmp_file.close()

            # Build prompt
            prompt = (
                f"Read the context file at {tmp_file.name} and analyze the trading session.\n"
                f"Stock: {symbol} ({strategy_name})\n"
                f"Search for recent news about this stock and include in your analysis.\n"
                f"Respond with valid JSON only."
            )

            cmd = [
                claude_path,
                "-p", prompt,
                "--output-format", "json",
                "--agent", "trading-analyst",
                "--permission-mode", "bypassPermissions",
            ]

            # Clean PM2 env vars
            env = os.environ.copy()
            for key in ["NODE_CHANNEL_FD", "NODE_CHANNEL_SERIALIZATION_MODE", "NODE_APP_INSTANCE"]:
                env.pop(key, None)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/home/hcpark/antigravity",
                env=env,
                start_new_session=True,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            except asyncio.TimeoutError:
                proc.kill()
                raise Exception("Claude CLI timed out (600s)")

            if proc.returncode != 0:
                err_msg = stderr.decode().strip() if stderr else "Unknown error"
                raise Exception(f"Claude CLI error: {err_msg[:300]}")

            raw = stdout.decode().strip()
            if not raw:
                raise Exception("Empty response from Claude CLI")

            # Parse Claude CLI JSON output (has result field)
            cli_output = json.loads(raw)
            result_text = cli_output.get("result", "")

            # Try to parse the result text as JSON
            return self._extract_json_from_response(result_text)

        finally:
            if tmp_file and os.path.exists(tmp_file.name):
                os.unlink(tmp_file.name)

    def _extract_json_from_response(self, text: str) -> Dict:
        """Extract JSON from Claude response, handling markdown code blocks."""
        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        import re
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object in text
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

        # Return a minimal valid response
        logger.warning(f"Could not parse JSON from Claude response, using raw text")
        return {
            "summary": text[:500],
            "grade": "N/A",
            "recommendations": [],
            "action": "유지",
            "risk_level": "medium",
            "news_articles": [],
        }

    async def _send_telegram_report(
        self, telegram: 'TelegramNotificationService',
        symbol: str, strategy_name: str,
        ai_result: Dict, is_paper: bool
    ):
        """Format and send analysis report via Telegram."""
        if not telegram.enabled:
            return

        mode_label = "모의" if is_paper else "실거래"
        grade = ai_result.get("grade", "N/A")
        grade_emoji = {"A": "\U0001f3c6", "B": "\u2705", "C": "\u26a0\ufe0f", "D": "\U0001f7e0", "F": "\u274c"}.get(grade, "\u2753")
        action = ai_result.get("action", "")
        action_emoji = {"\uc720\uc9c0": "\u2705", "\uc870\uc815": "\U0001f527", "\uc911\ub2e8": "\U0001f6d1"}.get(action, "\U0001f4cb")
        risk = ai_result.get("risk_level", "")
        risk_emoji = {"low": "\U0001f7e2", "medium": "\U0001f7e1", "high": "\U0001f534"}.get(risk, "\u26aa")

        header = f"""\U0001f4ca <b>AI \uc815\uae30 \ubd84\uc11d \ub9ac\ud3ec\ud2b8</b>

\U0001f4c8 <b>{symbol}</b> | {strategy_name}
\u251c \ubaa8\ub4dc: {mode_label}
\u2514 \ubd84\uc11d \uc2dc\uac04: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC

{grade_emoji} <b>\ub4f1\uae09: {grade}</b>
{action_emoji} <b>\uad8c\uc7a5: {action}</b>
{risk_emoji} <b>\uc704\ud5d8\ub3c4: {risk}</b>"""

        await telegram.send_message(header.strip())

        # Summary
        summary = ai_result.get("summary", "")
        if summary:
            await telegram.send_message(f"\U0001f4dd <b>\uc885\ud569 \ud3c9\uac00</b>\n\n{summary}")

        # News articles
        news = ai_result.get("news_articles", [])
        if news:
            news_text = "\U0001f4f0 <b>\uad00\ub828 \ub274\uc2a4</b>\n"
            for article in news[:5]:
                title = article.get("title", "")
                source = article.get("source", "")
                news_text += f"\n\u2022 {title} ({source})"
            await telegram.send_message(news_text)

        # Recommendations
        recs = ai_result.get("recommendations", [])
        if recs:
            rec_text = "\U0001f4a1 <b>\uad8c\uace0\uc0ac\ud56d</b>\n"
            for i, rec in enumerate(recs, 1):
                rec_text += f"\n{i}. {rec}"
            await telegram.send_message(rec_text)

    async def run_manual_analysis(self, session_id: str, user_id: int) -> Dict:
        """Run analysis manually (triggered from API)."""
        db: Session = SessionLocal()
        try:
            # Get session info
            row = db.execute(text("""
                SELECT id, symbol, strategy_name, strategy_config, is_paper, account_id
                FROM live_bot_sessions
                WHERE id = :sid
            """), {"sid": session_id}).fetchone()

            if not row:
                return {"error": "Session not found"}

            session_info = {
                "id": row[0], "symbol": row[1], "strategy_name": row[2],
                "strategy_config": row[3], "is_paper": row[4], "account_id": row[5]
            }

            # Create report with manual type
            from ..models.live_trading import generate_uuid
            report_id = generate_uuid()

            db.execute(text("""
                INSERT INTO ai_analysis_reports
                    (id, user_id, session_id, symbol, strategy_name,
                     report_type, status, strategy_config, created_at)
                VALUES
                    (:id, :user_id, :session_id, :symbol, :strategy_name,
                     'manual', 'running', :config, :now)
            """), {
                "id": report_id, "user_id": user_id,
                "session_id": session_id, "symbol": row[1], "strategy_name": row[2],
                "config": json.dumps(session_info["strategy_config"] or {}),
                "now": datetime.utcnow()
            })
            db.commit()

            # Run analysis (same pipeline as scheduled)
            await self._analyze_session_with_report(db, report_id, user_id, session_info)

            # Fetch completed report
            report = db.execute(text("""
                SELECT id, status, grade, ai_analysis, error_message, created_at, completed_at
                FROM ai_analysis_reports WHERE id = :rid
            """), {"rid": report_id}).fetchone()

            return {
                "report_id": report[0],
                "status": report[1],
                "grade": report[2],
                "error": report[4],
            }

        except Exception as e:
            logger.error(f"Manual analysis failed: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            db.close()

    async def _analyze_session_with_report(self, db: Session, report_id: str, user_id: int, session_info: Dict):
        """Run analysis for a session with an existing report record."""
        from .live_ai_evaluation import LiveAIEvaluationService
        from .telegram_service import TelegramNotificationService

        session_id = session_info["id"]
        symbol = session_info["symbol"]
        strategy_name = session_info["strategy_name"]
        strategy_config = session_info["strategy_config"] or {}
        is_paper = session_info["is_paper"]

        try:
            # Step 1: Collect data
            eval_service = LiveAIEvaluationService(db, user_id=user_id)
            live_stats = eval_service.collect_live_stats(session_id, symbol, n_cycles=10, is_paper=is_paper)
            if "error" in live_stats:
                raise Exception(f"Live stats error: {live_stats['error']}")

            backtest_stats = await eval_service.run_backtest_for_comparison(
                symbol, strategy_name, strategy_config, days=30
            )
            comparison = eval_service.compute_comparison(live_stats, backtest_stats)

            # Step 2: Build context for Claude agent
            context_data = {
                "session_info": {
                    "session_id": session_id, "symbol": symbol,
                    "strategy_name": strategy_name, "is_paper": is_paper,
                },
                "strategy_config": strategy_config,
                "trade_summary": live_stats,
                "backtest_comparison": comparison,
                "backtest_stats": backtest_stats,
            }

            # Step 3: Call Claude CLI agent
            ai_result = await self._call_claude_agent(context_data, symbol, strategy_name)

            # Step 4: Save results
            grade = ai_result.get("grade")
            recommendations = ai_result.get("recommendations", [])
            news_data = ai_result.get("news_articles", [])
            risk_level = ai_result.get("risk_level")
            action = ai_result.get("action")

            db.execute(text("""
                UPDATE ai_analysis_reports SET
                    status = 'completed',
                    trade_summary = :trade_summary,
                    backtest_comparison = :comparison,
                    ai_analysis = :ai_analysis,
                    ai_model = :ai_model,
                    news_data = :news_data,
                    grade = :grade,
                    key_findings = :key_findings,
                    recommendations = :recommendations,
                    risk_level = :risk_level,
                    action = :action,
                    completed_at = :now
                WHERE id = :rid
            """), {
                "trade_summary": json.dumps(live_stats),
                "comparison": json.dumps(comparison),
                "ai_analysis": json.dumps(ai_result, ensure_ascii=False),
                "ai_model": "claude-sonnet",
                "news_data": json.dumps(news_data),
                "grade": grade,
                "key_findings": json.dumps({"summary": ai_result.get("summary"), "performance_analysis": ai_result.get("performance_analysis")}),
                "recommendations": json.dumps(recommendations),
                "risk_level": risk_level,
                "action": action,
                "now": datetime.utcnow(),
                "rid": report_id,
            })
            db.commit()

            # Step 5: Telegram
            try:
                telegram = TelegramNotificationService(db, user_id=user_id)
                await self._send_telegram_report(telegram, symbol, strategy_name, ai_result, is_paper)
                db.execute(text("UPDATE ai_analysis_reports SET telegram_sent = TRUE WHERE id = :rid"), {"rid": report_id})
                db.commit()
            except Exception as e:
                logger.error(f"Telegram notification failed: {e}")

        except Exception as e:
            db.execute(text("""
                UPDATE ai_analysis_reports SET
                    status = 'failed', error_message = :err, completed_at = :now
                WHERE id = :rid
            """), {"err": str(e)[:500], "now": datetime.utcnow(), "rid": report_id})
            db.commit()
            raise

    @staticmethod
    def _compute_next_run(schedule_type: str, schedule_time: str, schedule_day: Optional[int] = None) -> datetime:
        """Compute next run time in UTC from KST schedule configuration."""
        try:
            hour, minute = map(int, schedule_time.split(":"))
        except (ValueError, AttributeError):
            hour, minute = 15, 40  # Default

        # Current KST time
        now_utc = datetime.utcnow()
        now_kst = now_utc + KST_OFFSET

        if schedule_type == "daily":
            # Next occurrence of HH:MM KST
            next_kst = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_kst <= now_kst:
                next_kst += timedelta(days=1)

        elif schedule_type == "weekly":
            day = schedule_day or 1  # 1=Monday
            next_kst = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # isoweekday: 1=Mon, 7=Sun
            days_ahead = day - now_kst.isoweekday()
            if days_ahead < 0 or (days_ahead == 0 and next_kst <= now_kst):
                days_ahead += 7
            next_kst += timedelta(days=days_ahead)

        elif schedule_type == "monthly":
            day = schedule_day or 1
            next_kst = now_kst.replace(day=min(day, 28), hour=hour, minute=minute, second=0, microsecond=0)
            if next_kst <= now_kst:
                # Move to next month
                if now_kst.month == 12:
                    next_kst = next_kst.replace(year=now_kst.year + 1, month=1)
                else:
                    next_kst = next_kst.replace(month=now_kst.month + 1)

        else:
            # Default: tomorrow same time
            next_kst = now_kst.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=1)

        # Convert KST → UTC
        return next_kst - KST_OFFSET


# Global singleton
analysis_scheduler = AnalysisScheduler()
