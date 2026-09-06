# Frigate on ubuntu-desktop

Git-backed Frigate configuration for continuous recording from five Tapo C225
cameras and the Nest stream supplied by Starling Home Hub.

## Design

- Each Tapo supplies one `stream1` connection for recording, live view and
  the low-rate camera/API frame. Frigate copies the original stream to disk.
  This avoids exhausting the cameras' stream capacity alongside Tapo Care and
  HomeKit.
- Frigate's bundled go2rtc owns those RTSP connections and restreams them
  internally, avoiding duplicate connections from Frigate components.
- Starling permits only one RTSP client. The Arc-backed `nest-transcoder` owns
  that connection, repairs the stream once, and publishes it to `nest-relay`.
  Frigate and Scrypted independently consume the repaired relay output.
- Starling's exported RTSP stream contains invalid H.264 frames and regressing
  timestamps. The faults were reproduced while decoding Starling directly
  with Scrypted stopped, in both Starling local and cloud streaming modes.
  Local mode is less damaged and must remain enabled.
- `nest-transcoder` deliberately decodes Starling in software with GStreamer's
  libav decoder, which can discard frames explicitly marked as corrupt. Its
  `videorate` stage holds the previous clean picture across the resulting
  gaps, so decoder concealment damage is never baked into the repaired
  stream. Raw video and audio then cross a local FIFO to FFmpeg; the Intel Arc
  A310's QSV media engine performs the expensive H.264 encode and produces a
  new 1080p15 H.264/AAC stream with a two-second GOP and regenerated
  timestamps. A small top-left `YYYY-MM-DD HH:MM:SS` overlay uses the host's
  `Europe/London` wall clock and matches the existing Tapo timestamp style.
  Starling has been observed
  switching between 15 and 24 FPS. Normalising to the lower rate preserves
  every frame in 15 FPS mode and drops excess frames in 24 FPS mode instead of
  manufacturing frames when the source slows down. `nest-relay` makes the
  repaired stream available inside the Compose network and on host loopback
  port `8556` for Scrypted. Frigate records directly from the relay and uses
  the same stream for go2rtc live view. The relay is not exposed to the LAN.
- The Arc also performs Frigate's H.264 decode/scaling through QSV and object
  inference through OpenVINO. The bundled MobileNetV2 model measured about
  4 ms per inference on this host. Detection and motion processing run at
  640x360 and 5 FPS on all six cameras. People, cats and dogs are tracked on
  every camera; cars are additionally tracked in the garage.
- The host udev rule installed by `install-arc-device-alias.sh` creates
  `/dev/dri/arc-a310-render` by PCI identity. Compose maps only that node into
  Frigate and the transcoder. It deliberately does not expose `/dev/dri`, the
  NVIDIA render node, or NVIDIA container capabilities, so the RTX 3080 stays
  assigned to the desktop and gaming/streaming workloads.
- Frigate receives only `CAP_PERFMON`, allowing its Intel telemetry helper to
  report Arc activity without privileged mode. The telemetry device is pinned
  to the mapped Arc render node.
- Frigate has a reduced CPU scheduling weight. Detection can use spare CPU at
  idle, while desktop games and Steam streaming take priority under contention;
  continuous recording still uses the cameras' original streams without video
  encoding.
- Recordings are retained continuously for 30 days.
- Event snapshots and Birdseye remain disabled. Recordings and go2rtc live
  streams retain their original 1920x1080 resolution; the lower resolution is
  used only for motion/object analysis.
- Port `8971` is the authenticated TLS UI/API. The unauthenticated port `5000`
  is deliberately not published. Docker binds the UI only to the stable LAN
  address. A persistent Tailscale Serve TCP forward exposes the same port to
  the tailnet after Tailscale is ready, so Docker does not fail during boot
  while waiting for `tailscale0`. RTSP and WebRTC remain LAN-only.

## Host paths

Runtime data is deliberately outside Komodo's disposable Git checkout:

- `/home/abhi/Docker/Frigate/data` - database, generated certificates and model cache
- `/home/abhi/Docker/Frigate/secrets` - camera and restream credentials
- `/srv/frigate` - dedicated surveillance disk mount and recordings

Do not deploy until `/srv/frigate` is mounted from the surveillance disk. If it
is merely an ordinary directory on the root filesystem, recordings could fill
the OS disk.

## Secrets

Create these files under `/home/abhi/Docker/Frigate/secrets`, mode `600`:

- `tapo_rtsp_user`
- `tapo_rtsp_password`
- `starling_nest_rtsp_url`
- `go2rtc_user`
- `go2rtc_password`
- `mqtt_password`

The Tapo values are the camera account created in the Tapo app, not the TP-Link
cloud account. Because they are embedded in RTSP URLs, percent-encode reserved
URL characters in both values. `starling_nest_rtsp_url` is the private RTSP
URL exported by Starling for the Nest camera. The transcoder must be Starling's
only client. Choose a separate random username and password for go2rtc clients. `mqtt_password` must
match the dedicated `frigate` account generated by the Git-backed Mosquitto
stack on the Pi.

For example, locally encode a value without printing it into shell history:

```sh
python3 -c 'import getpass, urllib.parse; print(urllib.parse.quote(getpass.getpass(), safe=""))'
```

## Deployment order

1. In the Tapo app, create a Camera Account under Advanced Settings for every
   C225. Until this is done, the cameras do not listen on RTSP port `554`.
   Reusing the same dedicated, non-cloud camera account on all five cameras
   keeps the Frigate secret set manageable.
2. Confirm that Ubuntu can reach port `554` on all five reserved camera IPs.
3. Partition, format and permanently mount the blank 4 TB surveillance disk at
   `/srv/frigate`. Use its filesystem UUID in `/etc/fstab` and do not use
   `nofail`; Frigate must never start against the underlying OS filesystem.
4. Install the stable Arc render-device alias:

   ```sh
   sudo ./install-arc-device-alias.sh
   ```

5. Create the runtime directories and secret files.
6. Validate with `docker compose --env-file .env config` from this directory.
7. Save Starling's private Nest RTSP URL in `starling_nest_rtsp_url`. Configure
   Scrypted's Nest camera to use `rtsp://127.0.0.1:8556/nest`, and select
   `FFmpeg Frame Generator` as the OpenCV motion decoder. Enable Starling's
   local network streaming mode; its cloud mode produces substantially more
   H.264 and timestamp errors.
8. Add a Git-backed Komodo stack using `UbuntuDesktop/Frigate/compose.yaml` and
   deploy it to `ubuntu-desktop`.
9. Configure the persistent tailnet listener once on `ubuntu-desktop`:

   ```sh
   tailscale serve --bg --yes --tcp=8971 tcp://192.168.0.180:8971
   ```

   `abhi` must first be configured as Tailscale's operator. Do not publish a
   second Docker port directly on the Tailscale address; that reintroduces the
   boot race this forward avoids.
10. Read the generated initial admin password with `docker logs frigate`.
11. Verify every live feed, recording playback, detection and disk growth
   before changing Scrypted or adding Home Assistant. Confirm that the RTX 3080
   remains in P8 with zero encoder/decoder utilisation while the cameras are
   active.

## Nest repair checks

The transcoder must remain Starling's only client. Scrypted reads the repaired
relay from `rtsp://127.0.0.1:8556/nest`; Frigate reads the same relay over the
private Compose network. Scrypted should use `FFmpeg Frame Generator` for its
OpenCV motion mixin so motion analysis does not depend on Python Codecs worker
processes.

MediaMTX publishes only a loopback host port for Scrypted. GStreamer owns
Starling's sole RTSP connection and discards corrupt decoded frames instead of
allowing their concealed pixels into the output. FFmpeg consumes uncompressed
audio/video locally and uses the Arc only for the new H.264 encode. An internal
watchdog probes the relay every 15 seconds and terminates both stages after two
consecutive failures, covering a source or publisher stall. The container then
retries after two seconds. MediaMTX disconnects Frigate's readers and
Frigate's normal watchdog reconnects when the repaired publisher returns. The
five Tapo recording paths are independent of both Nest services.

This design intentionally spends a small amount of CPU on one 1080p15 decode:
the prior all-QSV FFmpeg pipeline concealed damaged macroblocks and then
encoded the visible smear into an otherwise valid output stream. In deployment,
the clean decoder and Arc encoder together use roughly one quarter to one
third of a CPU core, while the RTX 3080 remains unavailable to the container.
The timestamp is drawn while each clean frame is already in system memory,
before upload to the Arc. Testing found no measurable additional CPU cost.
No motion mask is configured initially: its relative size and styling match
the five Tapo overlays that do not cause unwanted motion on this installation.
Use Frigate's Motion Boxes debug view before adding a mask if that behaviour
changes, because a mask should be evidence-driven and tightly scoped.

The repaired 15 FPS stream measured about 1.83 Mbit/s including audio, or
approximately 18.4 GiB/day for Nest. Its 3 Mbit/s video cap plus audio gives a
conservative upper bound of about 31.7 GiB/day. Together with the measured Tapo
rates, 30 days is projected at roughly 2.3 TiB under the measured rate and
about 2.7 TiB at the Nest upper bound, before filesystem and database overhead.
Both fit within the 3.7 TiB surveillance filesystem.

Useful checks:

```sh
docker compose ps
docker stats --no-stream frigate nest-transcoder
nvidia-smi --query-gpu=pstate,power.draw,utilization.encoder,utilization.decoder \
  --format=csv,noheader
readlink -f /dev/dri/arc-a310-render
docker exec frigate /usr/lib/ffmpeg/7.0/bin/ffmpeg \
  -hide_banner -loglevel error -xerror \
  -i /media/frigate/recordings/YYYY-MM-DD/HH/nest/SS.mp4 \
  -map 0:v:0 -map 0:a:0 -f null -
```

Frigate connects to the LAN-only Mosquitto broker on the Pi with a dedicated
account restricted to `frigate/#`. Home Assistant must use the same broker for
the official Frigate integration to populate its entities and events.
