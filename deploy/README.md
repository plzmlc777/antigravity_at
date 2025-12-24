# Deployment Scripts

> [!IMPORTANT]
> **PM2 is the standard deployment method.**
> Do NOT use the deprecated Systemd scripts.

## How to Deploy
Run the following command from the project root:
```bash
./deploy_with_pm2.sh
```

## Deprecated
The `deprecated/` directory contains old Systemd service files (`setup_services.sh`, `backend.service`, `frontend.service`).
These are kept for reference only and should not be used.
