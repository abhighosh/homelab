# Mosquitto MQTT broker

Git-backed, authenticated MQTT broker for Home Assistant and Frigate. The
listener binds only to the Pi's LAN address on port `1883`; it is not routed by
Nginx Proxy Manager and should not be exposed to the internet.

## Accounts

- `frigate` can read and write only `frigate/#`.
- `homeassistant` can read and write all topics so future MQTT integrations do
  not require redesigning the broker.
- `healthcheck` can read only `$SYS/broker/uptime`.

Anonymous connections are rejected. The tracked ACL contains no credentials.

## First deployment

Create the runtime credentials before validating or deploying the stack:

```sh
cd Mosquitto
./bootstrap-secrets.sh
docker compose config
```

The script creates random credentials under
`/home/abhi/Docker/Mosquitto/secrets`. It keeps individual plaintext client
passwords in ignored, mode-`600` files for configuring the clients and creates
a private, salted password database for the broker. Passwords are never
passed as command-line arguments.

Add this directory to Komodo as a Git-backed stack on the Pi (`Local`) and
deploy it only after the bootstrap completes. Runtime data remains at
`/home/abhi/Docker/Mosquitto/data`, outside Komodo's disposable Git checkout.

Check readiness without revealing a password:

```sh
docker inspect --format '{{.State.Health.Status}}' mosquitto
docker logs --tail 50 mosquitto
```

Do not publish port `1883` through Nginx Proxy Manager. If off-LAN MQTT clients
are ever needed, add TLS and a deliberately scoped Tailscale listener rather
than widening this listener.
