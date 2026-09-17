# Glances on ubuntu-nas

This stack supplies the authenticated `Ubuntu NAS` system widget on Homepage.
It reports host CPU, memory, temperature and uptime, plus capacity for the
dedicated Frigate recording disk mounted at `/srv/frigate`.

The web/API port is published on `61208` so the service survives a boot where
Docker starts before Tailscale has assigned `100.91.21.72`. Do not expose this
port through Nginx Proxy Manager; it is intended only for the trusted LAN and
tailnet and requires the `homepage` Glances account.

The untracked `secrets/homepage.pwd` file is the Glances password hash used by
that account. It must correspond to the plain password in
`Homepage/secrets/glances_password` on the Pi.

Deploy from this directory with:

```bash
docker compose pull
docker compose up -d
```
