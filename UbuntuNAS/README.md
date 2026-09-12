# ubuntu-nas

`ubuntu-nas` (`192.168.0.10`, Tailscale `100.91.21.72`) hosts the always-on
camera and emulator-repository workloads previously run on ubuntu-desktop.

- Frigate records to the dedicated HDD mounted at `/srv/frigate`; configuration
  and runtime state stay on the NVMe system disk.
- Scrypted consumes Frigate's repaired Nest stream and the camera restreams.
- Syncthing owns the emulator repository at `/srv/emulation` on NVMe.
- RomM catalogues `/srv/emulation/roms` read-only.

ubuntu-desktop remains a gaming machine and Syncthing client. Static emulator
content is receive-only there, while saves and states remain send-receive.
Frigate and Syncthing are enabled systemd services; Scrypted and RomM use Docker
restart policies. Runtime data, databases, indexes, credentials, and Tailscale
state are intentionally excluded from Git.
