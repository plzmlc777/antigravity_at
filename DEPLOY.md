# Deployment Protocol

**Standard Method:**
Always use the provided script to deploy changes. This script handles git pull, dependency installation, and service restart.

```bash
./deploy_with_pm2.sh
```

**What this script does:**
1. `git pull` (Updates code)
2. `npm install` (Frontend dependencies)
3. `pip install` (Backend dependencies)
4. `pm2 restart ecosystem.config.cjs` (Restarts services)

**Do NOT** manually restart services unless debugging specific issues.
