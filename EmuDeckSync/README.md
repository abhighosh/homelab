# EmuDeck synchronization

Rebuild and maintenance tooling for the Steam Deck and `ubuntu-desktop`
EmuDeck installation.

Nothing in this directory is required at runtime. Syncthing stores its live
configuration on each host, so removing the repository checkout would not stop
synchronization. These files are retained to document the design and make a
Deck reset or Ubuntu reinstall reproducible.

Do not commit ROMs, firmware, keys, saves, Syncthing certificates, device IDs,
passwords, or API credentials here.

## Hosts

- Steam Deck: user `deck`, EmuDeck data at `/home/deck/Emulation`. Its address
  is dynamic; use its current DHCP address or a local DNS name for SSH.
- Ubuntu Desktop: restricted user `gaming`, with `/home/gaming/Emulation`
  linked to SSD2 at
  `/mnt/0bab2145-d970-4175-8dcc-bb9f367c10a7/Emulation`.

Syncthing identifies peers by device ID rather than IP address. Local discovery
is enabled, while global discovery, relays, and NAT traversal are disabled.
Connections are restricted to `192.168.0.0/24`.

## Synchronization policy

| Data | Direction | Versioning |
| --- | --- | --- |
| ROMs, updates, HD packs, texture packs | Deck to Ubuntu | None |
| Eden keys and firmware | Deck to Ubuntu | Ubuntu retains received versions |
| Eden saves and profiles | Two way | One-year staggered history on both hosts |
| Other emulator saves and states | Two way | One-year staggered history on both hosts |

The non-Eden save definitions cover Cemu, Vita3K, Azahar, Citron, Dolphin,
DuckStation, melonDS, mGBA, PCSX2, PPSSPP, RetroArch, RPCS3, Ryujinx, ScummVM,
shadPS4, and Xenia. RPCS3 trophies and emulator save states are included.

`Emulation/saves` and `Emulation/bios` are not synchronized as whole folders:
they contain absolute, host-specific symlinks. The scripts pair the real target
directories explicitly. Emulator configuration, controller profiles, shader
caches, logs, ES-DE metadata, Steam shortcuts, and Xemu's mutable virtual disk
remain device-specific.

Cemu and Xenia keep saves below their ROM trees. `assets/roms.stignore`
excludes those paths from the bulk ROM share so they can be synchronized as
separate versioned save folders.

## Normal operation

Syncthing starts automatically in the background:

- Ubuntu: `syncthing@gaming.service`
- Steam Deck: the `deck` user's `syncthing.service`

Run `show-progress` as `deck` to inspect every folder. For a live view:

```sh
watch -n 10 ~/emudeck-sync-setup/show-progress
```

Exit an emulator before switching devices and wait for its save folders to
reach 100%. Do not run the same game on both hosts simultaneously. Ordinary
in-game saves are safer across emulator upgrades than save states.

Syncthing versioning is a recovery aid, not a complete backup. Save data still
requires an independent backup outside both synchronized hosts.

## Rebuild workflow

The scripts require the other host's Syncthing device ID as an argument where
shown. Device IDs deliberately remain outside Git.

1. Run `setup-ubuntu-host` with sudo. It validates that the expected SSD2 is
   mounted, installs current Ubuntu prerequisites, creates the `gaming` paths,
   and enables Syncthing. It does not modify `/etc/fstab`.
2. Run `setup-steamdeck` as `deck`. SteamOS is immutable, so it installs the
   checksum-pinned Syncthing binary under `~/.local/bin`. Review and update the
   paired version and checksum before using it for a future rebuild.
3. Exchange device IDs, then run `configure-steamdeck-sync UBUNTU_DEVICE_ID`
   and `configure-ubuntu-sync STEAM_DECK_DEVICE_ID` for the protected bulk
   Deck-to-Ubuntu seed.
4. Wait for the bulk seed to finish before installing or configuring emulators
   on Ubuntu.
5. Run `install-emudeck-as-gaming` from the Ubuntu `gaming` desktop session.
   Run `install-eden-as-gaming` if EmuDeck still cannot install Eden itself,
   then use EmuDeck's Eden reset/configuration action.
6. Run `configure-eden-steamdeck-sync UBUNTU_DEVICE_ID` and
   `configure-eden-ubuntu-sync STEAM_DECK_DEVICE_ID` to seed firmware, keys,
   saves, and profiles from the Deck.
7. Run `configure-save-sync-steamdeck UBUNTU_DEVICE_ID` and
   `configure-save-sync-ubuntu STEAM_DECK_DEVICE_ID` for the remaining save
   targets.
8. Confirm all save folders are at 100%, close all emulators, then run both
   `finalize-save-sync-*` scripts to enable two-way save synchronization.

The configure scripts intentionally begin with send-only on the Deck and
receive-only on Ubuntu. Do not skip directly to the finalizers: the protected
seed and timestamped Ubuntu backups prevent an empty or newly installed host
from deleting established saves.

## Repository contents

- `setup-*`: host bootstrap and systemd service installation.
- `install-*`: Ubuntu `gaming` account installers for EmuDeck and Eden.
- `configure-*-sync`: protected initial folder definitions and backups.
- `finalize-save-sync-*`: enable two-way save synchronization after validation.
- `show-progress`: read-only terminal status report.
- `assets/`: systemd, APT, and Syncthing ignore definitions.
