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

Komodo uses an ignored `komodo/compose.env` file containing deployment-specific settings:

```sh
cd Komodo/komodo
docker compose --env-file compose.env -f mongo.compose.yaml config
docker compose --env-file compose.env -f mongo.compose.yaml up -d
```

Komodo's sensitive values are supplied as Compose secrets rather than direct
environment variables. Copy `compose.env.example` to `compose.env`, then create
the following local files under `Komodo/komodo/secrets/`:

- `database_password`
- `jwt_secret`
- `webhook_secret`
- `aws_access_key_id`
- `aws_secret_access_key`

Keep `compose.env` and the `secrets` directory out of Git. Set the directory to
mode `700`, most files to `600`, and `database_password` to `644`; MongoDB reads
that mounted file after dropping privileges, while the directory's `700` mode
still prevents other host users from traversing to it.

## Repository policy

Compose definitions and safe application configuration belong in Git. Runtime data, databases, logs, certificates, backups, and environment files do not. Those ignored files still require a separate, tested backup process.

Before committing, use `git status --short --ignored` to confirm that no sensitive or generated files are being added.
