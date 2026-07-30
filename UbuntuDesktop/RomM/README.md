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

The bootstrap initializes the persistent `data/config/config.yml` file and is
safe to rerun without rotating existing credentials. Use `--rotate` only when
deliberately replacing both database and authentication secrets.

This is RomM Structure A: `/romm/library/roms/{platform}`. The filesystem
watcher waits ten minutes after Syncthing changes before running a quick scan.

## First deployment

1. Run `UbuntuDesktop/RomM/bootstrap-secrets.sh` on `ubuntu-desktop` from a
   current checkout of this repository.
2. Adopt `UbuntuDesktop/RomM/compose.yaml` into Komodo as a Git-backed stack on
   the `ubuntu-desktop` server and deploy it.
3. Open the RomM setup page and run the initial library scan.

Docker publishes RomM only on the host loopback address at port 8080. Configure
a persistent Tailscale Serve TCP forward once on `ubuntu-desktop`:

```sh
tailscale serve --bg --yes --tcp=8080 tcp://127.0.0.1:8080
```

`abhi` must first be configured as Tailscale's operator. Tailscale then exposes
`100.118.235.83:8080` only to the tailnet, and Nginx Proxy Manager can continue
to use that address. Keeping the Docker listener independent of `tailscale0`
allows RomM to start cleanly before Tailscale has acquired its address. Do not
replace the loopback binding with a direct Tailscale-address binding.

Back up `data/mariadb`, `data/resources`, `data/assets`, `data/config`, and the
ignored `secrets` directory. The ROM library already follows the separate
EmuDeck synchronization and backup policy.
