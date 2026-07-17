# Homelab infrastructure

Compose definitions, non-secret service configuration, and reproducible host
tooling for the Pi and `ubuntu-desktop`.

## Services

- AdGuard Home
- Homepage
- Glances on ubuntu-desktop
- Home Assistant
- Komodo with MongoDB and Periphery
- Nginx Proxy Manager
- ntfy
- Omada Controller
- Uptime Kuma

Each service is kept in its own directory. Run Compose commands from that directory so relative bind mounts resolve correctly.

## Host tooling

- `UbuntuDesktop/Gaming` contains the declarative Steam autostart setup for the
  restricted TV gaming account.
- `EmuDeckSync` documents and rebuilds the LAN-only Syncthing integration
  between the Steam Deck and Ubuntu EmuDeck installations. Its scripts are
  recovery and maintenance tools; the live synchronization does not depend on
  the repository checkout.

Services with configurable local time use the `Europe/London` IANA time zone so
scheduled tasks and timestamps consistently follow the host, including daylight
saving transitions.

Each Compose service has a health check. Komodo additionally gates Core startup
on a healthy MongoDB and Periphery startup on a healthy Core, so dependency
startup is based on readiness rather than container creation order.

Homepage uses an internal, read-only Docker API proxy to show container health
and resource statistics. The proxy is isolated on a private network shared only
with Homepage, permits selected Docker GET endpoints, and rejects POST requests.
Homepage also runs a local Glances instance on a separate internal-only network
for whole-host Pi metrics. It publishes no host port and has no access to the
Docker API proxy.
Service-widget credentials are mounted from ignored files under
`Homepage/secrets/` and referenced through `HOMEPAGE_FILE_*` substitutions; no
credential values belong in tracked YAML.
The Komodo widget uses a non-expiring API key owned by the dedicated `homepage`
service user. That user has only `Read` base permission on Server and Stack
resources; revoke and replace the key if the Homepage host is compromised.
The Uptime Kuma widget reads the internal `homepage` status page, which contains
the active homelab monitors and is not linked from the public dashboard.
The stable infrastructure on `ubuntu-desktop` is defined under
`UbuntuDesktop/`. Komodo deploys these as Git-backed stacks from this repository;
runtime data and Glances credentials remain ignored on the remote host. The
Homepage header reads host metrics from Glances 4 over its Tailscale-only,
authenticated API. SprintSlide remains in its application repository and is not
part of these infrastructure stacks.

```sh
cd UptimeKuma
docker compose config
docker compose up -d
```

## Shared proxy network

Nginx Proxy Manager and the local web frontends share an external Docker bridge
named `proxy`. NPM routes the Tailscale-only `*.abhighosh.co.uk` hosts to Docker
service names, so Homepage, Uptime Kuma, Komodo Core, and the AdGuard web UI do
not publish management ports on the host.

Create the network once before deploying these projects on a new host:

```sh
docker network create proxy
```

NPM remains the entry point on ports 80 and 443, bound only to the host's
Tailscale address (`100.99.54.40` by default). Its direct admin port is bound
only to `127.0.0.1:81`, while `nginxproxymanager.abhighosh.co.uk` continues to
proxy to the same UI through Tailscale. AdGuard DNS binds to both the LAN and
Tailscale addresses because the tailnet routes `abhighosh.co.uk` DNS queries to
this host. Its DoT and direct HTTPS ports bind only to the LAN address
(`192.168.0.220` by default). Omada's host-mode networking is an intentional
exception. Override the defaults with `TAILSCALE_IP` or `LAN_IP` when addresses
change.

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

The ntfy Git-backed Komodo stack keeps its runtime database at
`/home/abhi/Docker/Ntfy/data` by default rather than inside Komodo's disposable
repository checkout. Override `NTFY_DATA_PATH` in the Stack environment if the
host path changes.

Home Assistant follows the same pattern: its Git-backed Compose definition is
tracked under `HomeAssistant/`, while runtime configuration is kept at
`/home/abhi/Docker/HomeAssistant/config` by default. Override
`HOME_ASSISTANT_CONFIG_PATH` in the Stack environment if the host path changes.

Before committing, use `git status --short --ignored` to confirm that no sensitive or generated files are being added.

## Image update policy

Komodo is the update control plane for infrastructure on both `Local` and
`ubuntu-desktop`. Stable infrastructure stacks poll for changed image digests,
but automatic updates are disabled. Review upstream release notes and use a
deliberate Stack deploy/redeploy to apply an approved update.

The scheduled `Global Auto Update` procedure is disabled. SprintSlide is an
active development stack and is excluded from infrastructure update polling.
Scrypted no longer uses Watchtower; its updates are reviewed and deployed from
Komodo like the other infrastructure stacks.

Prefer exact image versions where upstream provides immutable release tags,
and documented major/minor or hardware-flavor tracks where a rolling channel is
required. Updating an exact tag is a source-controlled configuration change.

## Pi settings backup

`pi-settings-backup.timer` creates a filesystem snapshot on the SD card mounted
at `/mnt/pi-backup` every Sunday at 03:30, with up to 30 minutes of randomized
delay. The two newest successful snapshots are retained. Docker is stopped
while files are copied so service databases and volumes are consistent, then
started again even if the backup fails.

Snapshots include the root filesystem and `/boot/firmware`, while excluding
runtime virtual filesystems, caches, logs, and reproducible container image
layers. Later snapshots hard-link unchanged files to reduce SD usage.

Check the schedule and latest result with:

```sh
systemctl list-timers pi-settings-backup.timer
systemctl status pi-settings-backup.service
journalctl -u pi-settings-backup.service
```

Start an extra backup with `sudo systemctl start pi-settings-backup.service`.
Snapshot contents are ordinary files under `/mnt/pi-backup/snapshots/`; restore
individual settings with `rsync -aAXH --numeric-ids` while the affected service
is stopped. A full-system restore should be performed from rescue media onto a
fresh filesystem, followed by restoring the separate `boot-firmware` directory.
