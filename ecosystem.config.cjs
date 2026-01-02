module.exports = {
    apps: [
        {
            name: "at-backend",
            script: "python3",
            args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8001",
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
