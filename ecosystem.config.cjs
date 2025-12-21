module.exports = {
    apps: [
        {
            name: "at-backend",
            script: "uvicorn",
            args: "app.main:app --host 0.0.0.0 --port 8000",
            cwd: "./backend",
            interpreter: "../venv/bin/python", // Uses the virtual environment python
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
