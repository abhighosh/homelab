# Docker services

Compose definitions and non-secret configuration for the self-hosted services on this machine.

## Services

- AdGuard Home
- Homepage
- Komodo with MongoDB and Periphery
- Nginx Proxy Manager
- Omada Controller
- Uptime Kuma

Each service is kept in its own directory. Run Compose commands from that directory so relative bind mounts resolve correctly.

```sh
cd UptimeKuma
docker compose config
docker compose up -d
```

Komodo uses an ignored `komodo/compose.env` file containing deployment-specific settings and secrets:

```sh
cd Komodo/komodo
docker compose --env-file compose.env -f mongo.compose.yaml config
docker compose --env-file compose.env -f mongo.compose.yaml up -d
```

## Repository policy

Compose definitions and safe application configuration belong in Git. Runtime data, databases, logs, certificates, backups, and environment files do not. Those ignored files still require a separate, tested backup process.

Before committing, use `git status --short --ignored` to confirm that no sensitive or generated files are being added.
