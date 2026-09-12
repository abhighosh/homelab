# Syncthing on ubuntu-nas

The NAS is the always-on repository host. Static content such as ROMs,
firmware, updates, DLC, mods, HD packs, and texture packs is send-only from the
NAS. Saves, states, profiles, and trophies remain send-receive so progress can
move safely between gaming systems.

Repository data lives below `/srv/emulation`. Syncthing itself runs natively as
the `abhi` user; its private identity, index, and GUI credentials are runtime
state and are not stored in Git.

Install Syncthing from its official `stable-v2` APT channel and enable
`syncthing@abhi.service`. The GUI listens only on `127.0.0.1:8384`; persistent
Tailscale Serve forwards tailnet TCP port 8384 to it, and Nginx Proxy Manager
forwards `syncthing.abhighosh.co.uk` to `100.91.21.72:8384`. Native Syncthing
username/password authentication remains enabled. Its documented
`insecureSkipHostcheck` reverse-proxy option is enabled because the public Host
header cannot otherwise be rejected; network access is still tailnet-only.

During migration the old ubuntu-desktop identity is transferred to the NAS
only after Syncthing is stopped on ubuntu-desktop. Ubuntu-desktop is then reset
to a fresh identity and added back as a normal client. Never run both hosts
with the transferred identity at the same time.
