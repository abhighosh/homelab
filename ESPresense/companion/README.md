# Optional ESPresense Companion

Companion is not deployed for the current nearest-room pilot. This subproject
exists only for a future measured floor-plan deployment with enough nodes for
useful multilateration.

The image is pinned to `espresense/espresense-companion:2.1.2`. Runtime
configuration contains the MQTT password and remains ignored in
`ESPresense/data/`.

To prepare it in the future:

```sh
mkdir -p ESPresense/data
cp ESPresense/companion/config.yaml.example ESPresense/data/config.yaml
chmod 700 ESPresense/data
chmod 600 ESPresense/data/config.yaml
```

Insert the local `espresense` MQTT password, measure the floor plan and node
coordinates, then validate from this directory:

```sh
cd ESPresense/companion
docker compose config
docker compose up -d
```

The UI binds to the configured Tailscale address on port `8267`; LAN nodes use
port `8268` for Companion firmware services. Do not expose either port publicly.
