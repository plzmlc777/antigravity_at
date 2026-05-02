"""Mint a 7-day JWT for the paper-scheduler service user.

Used by SAS runner scripts (run_paper_scheduler.sh, run_live_monitor.sh) to
authenticate /live/* API calls without going through the interactive login flow.

The service user `paper-scheduler@internal` (id=9) has `active_session_id=NULL`
so the single-session check in app.api.auth is bypassed (any JWT with matching
subject is accepted; sid claim is not required).

Usage:
    cd backend && PYTHONPATH=. ./venv/bin/python3 issue_service_token.py
    # → prints a single JWT line on stdout

Output is captured by the SAS runner and exported as BACKEND_SERVICE_TOKEN.
"""
from datetime import timedelta
from app.core.security import create_access_token

SERVICE_EMAIL = "paper-scheduler@internal"
EXPIRES = timedelta(days=7)

token = create_access_token(
    subject=SERVICE_EMAIL,
    expires_delta=EXPIRES,
    session_id=None,
)
print(token)
