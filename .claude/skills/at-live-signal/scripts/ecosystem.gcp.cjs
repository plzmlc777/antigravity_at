/**
 * GCP at-asia skill-runner fleet — one runner per live paper session.
 *
 * Each session in DB has strategy_name='noop' so the backend LiveTradingEngine
 * generates zero signals; these PM2 apps run the real strategy externally and
 * push signals via the /submit-signal API.
 *
 * Start all: pm2 start ecosystem.gcp.cjs
 * Start one: pm2 start ecosystem.gcp.cjs --only skill-runner-btc-7x
 */
const SCRIPT_DIR = '/home/hcpark/antigravity/.claude/skills/at-live-signal/scripts';
const PYTHON = '/home/hcpark/antigravity/backend/venv/bin/python3';

const common = {
  script: PYTHON,
  cwd: SCRIPT_DIR,
  interpreter: 'none',
  autorestart: true,
  max_restarts: 10,
  restart_delay: 5000,
  env: {
    PYTHONPATH: `${SCRIPT_DIR}:/home/hcpark/antigravity/backend`,
    PYTHONDONTWRITEBYTECODE: '1',
  },
};

module.exports = {
  apps: [
    {
      ...common,
      name: 'skill-runner-btc-7x',
      args: `${SCRIPT_DIR}/run_strategy.py --session-id 3b8f15de-525b-425f-8edc-2f5fe3993fd2 --strategy dip_martingale --api-url http://localhost:8001 --mode ws`,
    },
    {
      ...common,
      name: 'skill-runner-btc-10x',
      args: `${SCRIPT_DIR}/run_strategy.py --session-id 6260d7f9-8044-48c9-ae11-4f16e93d401f --strategy dip_martingale --api-url http://localhost:8001 --mode ws`,
    },
    {
      ...common,
      name: 'skill-runner-eth-3x',
      args: `${SCRIPT_DIR}/run_strategy.py --session-id 6c040d03-b1ee-447c-be97-7fade30c772d --strategy time_momentum --api-url http://localhost:8001 --mode ws`,
    },
  ],
};
