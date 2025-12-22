module.exports = {
    apps: [
        {
            name: "at-backend",
            script: "./venv/bin/python",
            args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8000",
            cwd: "./backend",
            env: {
                PYTHONPATH: "."
            }
        },
        {
            name: "at-frontend",
            script: "npm",
            args: "run dev -- --host 0.0.0.0",
            cwd: "./frontend",
            env: {
                NODE_ENV: "development"
            }
        }
    ]
};
