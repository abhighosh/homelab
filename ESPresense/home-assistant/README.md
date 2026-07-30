# Home Assistant presence configuration

These files are secret-free reference copies of the live configuration under
`HomeAssistant/config/`, which remains ignored because it also contains runtime
state, integration storage, databases, and credentials.

Files:

- `sensors.yaml.example`: ESPresense `mqtt_room` sensors.
- `templates.yaml.example`: derived cat room occupancy sensors.
- `input_text.yaml.example`: nine Home Assistant-editable panel action labels.
- `input_boolean.yaml.example`: Roborock schedule master and weekday switches.
- `input_datetime.yaml.example`: editable Roborock schedule start time.
- `automations.yaml.example`: the panel action router and Roborock scheduler.
- `scripts.yaml.example`: the nine UI-editable actions run by panel buttons.
- `presence-dashboard.yaml.example`: the sidebar Presence dashboard.
- `schedules-dashboard.yaml.example`: Roborock and Husqvarna schedule controls.
- `panel-dashboard.yaml.example`: the standalone display configuration.
- `configuration.yaml.example`: the required include, dashboard, and HomeKit
  sections from `configuration.yaml`.

To reproduce the current configuration:

1. Merge `configuration.yaml.example` into the live
   `HomeAssistant/config/configuration.yaml`; do not overwrite unrelated
   top-level keys.
2. Copy the other examples to the corresponding live filenames without
   the `.example` suffix.
3. Do not add Home Assistant notification automations. Alerts are configured
   per occupancy accessory in Apple Home.
4. Validate before restarting:

   ```sh
   docker exec homeassistant \
     python -m homeassistant --script check_config --config /config
   ```

5. Restart Home Assistant only after validation passes.

The `Cat Safety` HomeKit bridge is a separate YAML-managed bridge on port
`21065`. The existing UI-managed HomeKit bridge on port `21064` is unrelated and
must not be replaced with this example.

The iPhone IRK and MQTT password are intentionally absent. ESPresense resolves
the iPhone to the safe alias `phone:abhi-iphone` before publishing measurements.

The panel consumes two compact Home Assistant-managed strings:

- `sensor.cat_panel_room_tiles`: up to twelve `Label:cat-code:phone-code` entries
  separated by `|`; `0` is absent, `1` present/safe, `2` cat
  present/forbidden, and `?` unknown. The current eleven rooms occupy an
  eleven-tile 4-by-3 grid on the CrowPanel.
- `sensor.panel_action_labels`: combines the nine individual action-label
  helpers for the display.

Panel buttons emit `esphome.cat_panel_action` with a slot number. Edit the
matching **Panel action 1–9** script under **Settings → Automations & scenes →
Scripts** to change what a slot does. Edit labels on **Presence → Panel**; no
ESPHome reflash is required.

CrowPanel action 4 toggles `input_boolean.roborock_schedule_enabled`; action 5
toggles `switch.garden_rodney_enable_schedule`. Configure the Roborock start
time and enabled weekdays on **Schedules → Roborock schedule**. The same
dashboard exposes Husqvarna's native schedule and mower settings. The Home
Assistant automation starts `vacuum.roborock_q7_l5` only when both the master
switch and the current weekday are enabled. Disabling the switch affects future
starts and does not stop a clean already in progress.

The separate **Panel Configuration** dashboard owns the nine action labels and
scripts; presence tracking is kept in the standalone **Presence** dashboard.
