# RomM on ubuntu-desktop

RomM catalogues the authoritative EmuDeck ROM library on SSD2. The library is
mounted read-only, so RomM cannot rename, upload, or delete files used by the
gaming PC, Steam Deck, or TrimUI Brick. Saves, states, firmware, and emulator
configuration are outside the mount and remain part of the existing EmuDeck
Syncthing design.

## Storage

- ROM source: `/mnt/0bab2145-d970-4175-8dcc-bb9f367c10a7/Emulation/roms`
- RomM mount: `/romm/library/roms` (read-only)
- Runtime data: `/home/abhi/Docker/RomM/data`
- Runtime secrets: `/home/abhi/Docker/RomM/secrets`

This is RomM Structure A: `/romm/library/roms/{platform}`. The filesystem
watcher waits ten minutes after Syncthing changes before running a quick scan.

## First deployment

1. Run `UbuntuDesktop/RomM/bootstrap-secrets.sh` on `ubuntu-desktop` from a
   current checkout of this repository.
2. Adopt `UbuntuDesktop/RomM/compose.yaml` into Komodo as a Git-backed stack on
   the `ubuntu-desktop` server and deploy it.
3. Open the RomM setup page and run the initial library scan.

RomM listens only on Ubuntu Desktop's Tailscale address at port 8080. Nginx
Proxy Manager can route a Tailscale-only hostname to `100.118.235.83:8080`.

Back up `data/mariadb`, `data/resources`, `data/assets`, `data/config`, and the
ignored `secrets` directory. The ROM library already follows the separate
EmuDeck synchronization and backup policy.
