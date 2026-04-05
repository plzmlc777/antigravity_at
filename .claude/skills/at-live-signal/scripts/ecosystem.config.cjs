const SCRIPT_DIR = '/home/hcpark/antigravity/.claude/skills/at-live-signal/scripts';

module.exports = {
  apps: [{
    name: 'skill-runner',
    script: '/home/hcpark/antigravity/backend/venv/bin/python3',
    args: `${SCRIPT_DIR}/run_strategy.py --session-id skill-test-001 --strategy rsi_martingale --api-url http://localhost:8001`,
    cwd: SCRIPT_DIR,
    interpreter: 'none',
    autorestart: true,
    max_restarts: 5,
    restart_delay: 5000,
    env: {
      PYTHONPATH: `${SCRIPT_DIR}:/home/hcpark/antigravity/backend`,
      PYTHONDONTWRITEBYTECODE: '1',
    },
  }],
};
