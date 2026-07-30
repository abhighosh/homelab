# ESPHome touchscreen panel

The first ELEGOO 2.8-inch touchscreen is a dedicated Home Assistant panel
running ESPHome with LVGL. It does not run ESPresense or act as a room scanner.

The larger dashboard is an Elecrow CrowPanel Advance 5.0, model `DIS02050A`,
with an ESP32-S3-WROOM-1-N16R8, 16 MB flash, 8 MB octal PSRAM, an 800 x 480
ST7262 RGB display, and GT911 capacitive touch. The current V1.3 board uses the
same software and pin map as V1.2.

Its first bench image is `config/crowpanel-hardware-test.yaml`. It uses
Elecrow's V1.2/V1.3 RGB timings and pin map and sends the required commands to
the onboard controller at I2C address `0x30` to enable touch and illuminate the
backlight. ESPHome's standard LVGL test page verifies:

- the full 800 x 480 image and correct RGB colour order;
- GT911 touch alignment;
- 8 MB PSRAM operation;
- Wi-Fi, encrypted API, logs, and OTA readiness.

For the bench test it reuses the existing panel secrets without exposing them
in source control. Give the deployed CrowPanel unique API, OTA, and fallback-AP
credentials before adding it permanently to Home Assistant.

Validate and compile the bench image with:

```sh
cd ESPresense/display
docker compose run --rm esphome config crowpanel-hardware-test.yaml
docker compose run --rm esphome compile crowpanel-hardware-test.yaml
```

Power this panel from a stable 5 V / 2 A source or powered data-capable USB
connection. If the screen remains dark despite successful serial logs, confirm
the PCB revision: V1.0/V1.1 use different backlight commands.

The live CrowPanel dashboard has Overview, Presence, Climate, and Actions
pages. Presence uses a 4-by-3 grid populated from Home Assistant, currently
showing all eleven deployed ESPresense rooms. The Overview includes cat and
iPhone location, weather and temperatures, heating/hot-water state, plus
Roborock and Husqvarna status, battery level, and schedule controls. Camera
snapshots are intentionally excluded: decoding and retaining multiple images
leaves insufficient memory headroom for stable operation.
After 60 seconds without touch, the board controller reduces the backlight to a
low idle level while LVGL remains active and continues rendering Home Assistant
state changes. This supplied panel behaves like Elecrow's legacy backlight
controller (`5` off through `16` maximum), so the dashboard uses `6` while idle
and `16` while active. A tap restores normal brightness. A forbidden or
not-detected cat state keeps the display bright so the safety warning remains
visible.

## Identified hardware

The supplied description matches ELEGOO model `GE-GYE-EB-008`, a variation of
the LCDWIKI `E32R28T` / original `ESP32-2432S028R` design:

- classic ESP32-WROOM-32E module;
- `N4` denotes 4 MB flash;
- no external PSRAM;
- 240 x 320 TFT using an ILI9341 controller;
- XPT2046 resistive-touch controller;
- CH340 USB-to-serial interface.

Expected pin map:

| Function | GPIO |
| --- | ---: |
| LCD CS | 15 |
| LCD DC/RS | 2 |
| LCD SCK | 14 |
| LCD MOSI | 13 |
| LCD MISO | 12 |
| LCD reset | shared with ESP32 EN |
| Backlight | 21 |
| Touch SCK | 25 |
| Touch MOSI | 32 |
| Touch MISO | 39 |
| Touch CS | 33 |
| Touch IRQ | 36 |

The module marking alone cannot distinguish every visually similar board.
Before flashing, check whether the PCB itself says `E32R28T`,
`ESP32-2432S028R`, or another revision. A board marked `E32R28T-1` uses an
ST7789P3 display and will need a different display profile. Other CYD revisions
also exist with ILI9342-family displays. An incorrect display profile normally
produces a white or garbled screen; it does not overwrite the controller.

## First hardware test

The tracked `config/cat-panel-hardware-test.yaml` deliberately enables only:

- the ILI9341 display at a conservative 10 MHz;
- the GPIO21 backlight;
- ESPHome's standard LVGL colour/geometry test;
- encrypted Home Assistant API, protected OTA, and a fallback setup hotspot.

Touch and Home Assistant data are intentionally absent from this first image.
This separates LCD/controller problems from calibration and dashboard logic.

The confirmed board can then run `config/cat-panel-touch-calibration.yaml`.
This adds the XPT2046 on its separate SPI bus and logs raw coordinates whenever
the screen is touched. The first panel measured X `280..3800` and Y
`200..3730`; its raw X axis is reversed, so the configuration mirrors X.

The initial setup creates a unique ignored `config/secrets.yaml`. When
reproducing the project on another host, copy the example and replace all three
values:

```sh
cd ESPresense/display
cp config/secrets.yaml.example config/secrets.yaml
# Replace all three values in config/secrets.yaml.
docker compose run --rm esphome config cat-panel-hardware-test.yaml
```

Compile it with:

```sh
docker compose run --rm esphome compile cat-panel-hardware-test.yaml
```

The first flash is performed from Chrome on the Mac. Download the generated
factory image from the build host, then use
[ESPHome Web](https://web.esphome.io/) with the board connected by a
data-capable USB cable. Once flashed, join the `Cat Panel 01 Setup` Wi-Fi
network and use its captive portal to supply the home Wi-Fi credentials.
Subsequent updates use OTA.

## Data path

Use ESPHome's encrypted native API to import Home Assistant entities:

- `sensor.cat_collar_room`
- `sensor.abhi_iphone_room`
- the three `binary_sensor.cat_in_*` occupancy sensors
- selected weather, temperature, door, and alarm entities
- ESPresense node health entities once those are normalized in Home Assistant

No MQTT credential is required on the display. If Home Assistant is
unavailable, the interface must visibly mark imported data unavailable rather
than retaining an apparently current location indefinitely.

## Interface

`config/cat-panel.yaml` is the live landscape dashboard. Its persistent footer
switches between:

- **Presence**: cat safety/location, iPhone location, and a compact 5-by-2 room
  grid.
- **Actions**: nine Home Assistant-routed action buttons.

The display starts dark. Touch wakes it for 30 seconds while the cat is safe.
Confirmed forbidden occupancy or a confirmed not-detected state wakes it and
keeps it lit continuously in red. The ten-second confirmation period is amber.
Touch never clears the underlying occupancy.

Routine changes are Home Assistant-driven:

- `binary_sensor.cat_in_forbidden_room` owns the safety decision.
- `sensor.cat_panel_room_tiles` supplies up to ten pipe-separated
  `Label:code` entries. Codes are `0` empty, `1` occupied/safe, `2`
  occupied/forbidden, and `?` unknown.
- `sensor.panel_action_labels` combines nine editable
  `input_text.panel_action_*_label` helpers.
- Button presses fire `esphome.cat_panel_action` with `slot` `1` through `9`;
  the Home Assistant automation routes those slots to editable
  `script.panel_action_1` through `script.panel_action_9` scripts.

Changing labels, room membership, safety rules, or routed automations therefore
does not require reflashing the ESP32. Firmware changes are only needed for
layout or hardware behaviour.

## Bring-up order

1. Confirm the PCB model/revision text.
2. Validate, compile, and flash the minimal hardware test.
3. Verify display controller, colours, rotation, and backlight.
4. Add XPT2046 and log raw touch coordinates at every edge.
5. Calibrate touch in the final screen orientation.
6. Import the presence entities and handle unavailable states.
7. Add the final pages and alert styling.
8. Verify the safe-room touch timeout and continuous forbidden-room backlight.
9. Test Wi-Fi loss, Home Assistant restart, stale collar data, touch accuracy,
   and overnight operation.

For this board without PSRAM, start LVGL with a 25% render buffer and a modest
widget count. Keep BLE proxying disabled until display stability and memory
headroom are measured.

References:

- [LCDWIKI E32R28T SDK and schematic](https://www.lcdwiki.com/zh/2.8inch_ESP32-32E_Display)
- [ESPHome MIPI SPI displays](https://esphome.io/components/display/mipi_spi/)
- [ESPHome LVGL](https://esphome.io/components/lvgl/)
- [ESPHome touchscreen calibration](https://esphome.io/components/touchscreen/)
- [XPT2046 touchscreen](https://esphome.io/components/touchscreen/xpt2046/)
