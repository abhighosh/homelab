# ESPresense cat-presence pilot

This project tracks a collar-mounted iBeacon and an enrolled iPhone using
dedicated ESPresense room scanners. Home Assistant selects the scanner reporting
the shortest recent BLE distance, derives cat occupancy entities, and exposes
those entities through a dedicated HomeKit bridge.

The current ground-to-second-floor deployment uses nine M5 ATOM Lite boards
and two generic ELEGOO ESP32 boards. The five newest M5 nodes are deployed with
receiver calibration still pending:

| Room | Board | Address | Role | Rx adjustment |
| --- | --- | --- | --- | ---: |
| `ground_hallway` | M5 ATOM Lite | `192.168.0.14` | Allowed room and reference node | `0 dB` |
| `snug` | M5 ATOM Lite | `192.168.0.16` | Forbidden room | `-2 dB` |
| `kitchen` | M5 ATOM Lite | `192.168.0.21` | Allowed room | `0 dB` (validation deferred) |
| `first_floor_hallway` | ELEGOO generic ESP32 | `192.168.0.8` | Allowed room | `0 dB` (validation deferred) |
| `master_bedroom` | ELEGOO generic ESP32 | `192.168.0.9` | Forbidden room | `0 dB` (validation deferred) |
| `second_floor_hallway` | M5 ATOM Lite | `192.168.0.17` | Allowed room | `0 dB` (validation deferred) |
| `ground_floor_living_room` | M5 ATOM Lite | `192.168.0.27` | Forbidden; deployed | `0 dB` (calibration deferred) |
| `first_floor_guest_double_bedroom` | M5 ATOM Lite | `192.168.0.28` | Forbidden; deployed | `0 dB` (calibration deferred) |
| `first_floor_study` | M5 ATOM Lite | `192.168.0.29` | Forbidden; deployed | `0 dB` (calibration deferred) |
| `second_floor_green_bedroom` | M5 ATOM Lite | `192.168.0.30` | Forbidden; deployed | `0 dB` (calibration deferred) |
| `second_floor_guest_ensuite` | M5 ATOM Lite | `192.168.0.31` | Forbidden; deployed | `0 dB` (calibration deferred) |

One generic ELEGOO board and the remaining touchscreen boards are reserved for
later expansion.
Do not reuse a room name: ESPresense derives its MQTT client ID from it, so
duplicate names repeatedly disconnect one another.

## Architecture

```text
Holy-IOT iBeacon / enrolled iPhone
                  |
       ESPresense room scanners
                  |
       Mosquitto 192.168.0.220:1883
                  |
        Home Assistant mqtt_room
                  |
   Presence dashboard + Cat Safety HomeKit bridge
```

An ESPresense scanner is not a Home Assistant Bluetooth Proxy. Each board runs
one firmware image; flashing ESPHome or custom display firmware replaces
ESPresense.

## MQTT

All scanners use the dedicated `espresense` account. The tracked Mosquitto ACL
permits that account to use `espresense/#`, publish Home Assistant discovery,
and read Home Assistant's discovery status.

Provisioning values:

- Broker: `192.168.0.220`
- Port: `1883`
- Username: `espresense` (note the spelling)
- Password: ignored file `Mosquitto/secrets/espresense_password`
- Transport: unencrypted MQTT on the trusted LAN only

Regenerate the broker database only when accounts change:

```sh
cd Mosquitto
./bootstrap-secrets.sh
docker compose config
docker compose up -d
```

Never commit the generated password files or expose port 1883 publicly.

## Firmware and node provisioning

The M5 ATOM Lite nodes run the `m5atom` firmware flavour. The two generic
ELEGOO boards use the standard `esp32` flavour and identify as
`ESP32-D0WD-V3`. The current stable ESPresense release is `4.0.6`.

Flash with Chrome using the official
[web installer](https://espresense.com/firmware). Configure a unique lowercase
room slug, 2.4 GHz Wi-Fi, and the MQTT values above. Enable per-device
publishing so Home Assistant's `mqtt_room` sensors receive
`espresense/devices/<device>/<room>` measurements.

The pilot uses:

- maximum distance `16 m`;
- absorption factor `2.7`;
- ground-hallway, kitchen, and second-floor Rx adjustment `0`;
- snug Rx adjustment `-2`.

The collar advertises every 500 ms with calibrated `rssi@1m` of `-66 dBm`.
The snug offset was measured but its two-metre validation was intentionally
deferred. Revalidate placement and offsets before treating BLE distance as a
physical measurement or adding doorway-sensitive automations.

## Tracked identities

The retained fleet configuration assigns:

- `cat_collar` / `Cat Collar` to the Holy-IOT iBeacon;
- `phone:abhi-iphone` / `abhi_iphone` to the enrolled iPhone.

The collar's stable fingerprint and non-secret pilot metadata are recorded in
[`inventory.yaml`](inventory.yaml). The iPhone IRK is deliberately excluded
from Git because it is a private device identity key. It remains stored on the
nodes and in retained MQTT configuration.

## Home Assistant

The live Home Assistant configuration is runtime state and remains ignored
under `HomeAssistant/config/`. Reproducible, secret-free copies of the presence
configuration live under [`home-assistant/`](home-assistant/).

The current entities are:

- `sensor.cat_collar_room`
- `sensor.abhi_iphone_room`
- `binary_sensor.cat_in_snug`
- `binary_sensor.cat_in_ground_hallway`
- `binary_sensor.cat_in_kitchen`
- `binary_sensor.cat_in_first_floor_hallway`
- `binary_sensor.cat_in_master_bedroom`
- `binary_sensor.cat_in_second_floor_hallway`
- `binary_sensor.cat_not_detected`

The binary sensors use the `occupancy` device class. Safety-critical Snug and
general forbidden-room occupancy require ten continuous seconds before
asserting, suppressing doorway and transient nearest-node flips. A missing or
unavailable collar is also unsafe after that confirmation period. The raw room
sensor remains immediate for diagnostics, and a ten-second off-delay on
room-specific occupancy suppresses dropouts. Home Assistant notification
automations are intentionally absent. Apple Home
notifications are configured on the occupancy accessories exposed by the
separate `Cat Safety` bridge on port `21065`.

See [`home-assistant/README.md`](home-assistant/README.md) for installation and
validation.

## Touchscreen display

Touchscreen boards will run ESPHome and LVGL as dedicated Home Assistant panels,
not ESPresense. ESPHome's encrypted native API will import the room and
occupancy entities directly, so no display-specific MQTT account or bridge
automation is required.

The supplied board has been identified provisionally as ELEGOO
`GE-GYE-EB-008`, using the original 4 MB, no-PSRAM CYD/E32R28T pinout with an
ILI9341 display and XPT2046 resistive touch controller. A tracked ESPHome
hardware-test image and its bring-up sequence live under
[`display/`](display/README.md). Confirm the PCB revision text before its first
flash because later dual-USB revisions can use a different display controller.

## Optional Companion

ESPresense Companion is not deployed and is not needed for nearest-room
tracking. Its pinned Compose definition is isolated under
[`companion/`](companion/) for a possible future coordinate/floor-plan project.
Do not deploy it until the house has enough measured nodes for useful
trilateration.

## Operational checks

Listen for room status:

```sh
docker exec mosquitto mosquitto_sub \
  -h 127.0.0.1 -u espresense \
  -P "$(sed -n '1p' Mosquitto/secrets/espresense_password)" \
  -t 'espresense/rooms/+/status' -v -W 10
```

Listen for the collar:

```sh
docker exec mosquitto mosquitto_sub \
  -h 127.0.0.1 -u espresense \
  -P "$(sed -n '1p' Mosquitto/secrets/espresense_password)" \
  -t 'espresense/devices/cat_collar/#' -v -W 10
```

Official references:

- [ESPresense firmware](https://espresense.com/firmware)
- [MQTT topics](https://espresense.com/configuration/mqtt/)
- [Calibration](https://espresense.com/guides/calibration/)
- [Device enrollment](https://espresense.com/guides/enrolling-devices/)
- [Home Assistant MQTT room](https://www.home-assistant.io/integrations/mqtt_room)
