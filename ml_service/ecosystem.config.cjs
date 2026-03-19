module.exports = {
  apps: [{
    name: "ml-service",
    script: "python3",
    args: "-m uvicorn main:app --host 0.0.0.0 --port 8002",
    cwd: "/home/hcpark/antigravity/ml_service",
    interpreter: "none",
    autorestart: true,
    max_restarts: 10,
    env: {
      PYTHONUNBUFFERED: "1",
    }
  }]
};
