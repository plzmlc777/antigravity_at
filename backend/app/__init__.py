# Bootstrap: add at-live-signal skill scripts to sys.path so that
# `import strategies.<name>` resolves to the canonical strategy
# implementations now owned by the at-live-signal skill.
#
# Backend code that needs strategy classes should import them as
# `from strategies.base import BaseStrategy`
# `from strategies.rsi_martingale import RSIMartingaleStrategy`
# etc. — NOT from the (now-removed) `app.strategies` package.
import sys
from pathlib import Path

_SKILL_SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "at-live-signal" / "scripts"
if _SKILL_SCRIPTS.is_dir() and str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))
