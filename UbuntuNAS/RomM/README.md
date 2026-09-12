# RomM on ubuntu-nas

RomM catalogues the NAS-owned emulator repository at `/srv/emulation/roms`.
The library is mounted read-only, so RomM cannot rename, upload, or delete
files shared to gaming clients by Syncthing.

Runtime state and secrets live below `/home/abhi/Docker/RomM` on the NAS. The
existing database, assets, resources, configuration, and secrets are migrated
from ubuntu-desktop rather than regenerated.

RomM listens only on `127.0.0.1:8080`. Persistent Tailscale Serve forwards
tailnet TCP port 8080 to that listener, and Nginx Proxy Manager forwards
`romm.abhighosh.co.uk` to `100.91.21.72:8080`. Do not expose MariaDB.

The persistent `data/config/config.yml` contains the existing EmuDeck catalogue
exclusions and must be retained during migration.
