# Frigate on ubuntu-desktop

Git-backed Frigate configuration for continuous recording from five Tapo C225
cameras and the Nest stream supplied by Starling Home Hub.

## Design

- Each Tapo supplies `stream1` to the recorder and live view, and `stream2` to
  motion/object detection.
- Frigate's bundled go2rtc owns those RTSP connections and restreams them
  internally, avoiding duplicate connections from Frigate components.
- The Nest camera initially has one additional consumer from Frigate. After the
  feed is proven stable, Scrypted can consume Frigate's authenticated
  `rtsp://192.168.0.180:8554/nest` restream instead of connecting to Starling
  directly.
- Recordings are retained continuously for 14 days. Alert and detection footage
  is retained for 30 days.
- NVIDIA NVDEC handles video decoding and TensorRT handles object detection.
- Port `8971` is the authenticated TLS UI/API. The unauthenticated port `5000`
  is deliberately not published.

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
- `nest_rtsp_url`
- `go2rtc_user`
- `go2rtc_password`

The Tapo values are the camera account created in the Tapo app, not the TP-Link
cloud account. Because they are embedded in RTSP URLs, percent-encode reserved
URL characters in both values. `nest_rtsp_url` is the complete RTSP URL exposed
by Starling. Choose a separate random username and password for go2rtc clients.

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
4. Create the runtime directories and secret files.
5. Validate with `docker compose --env-file .env config` from this directory.
6. Add a Git-backed Komodo stack using `UbuntuDesktop/Frigate/compose.yaml` and
   deploy it to `ubuntu-desktop`.
7. The first start builds the TensorRT model and can take several minutes. Read
   the generated initial admin password with `docker logs frigate`.
8. Verify every live feed, NVDEC/TensorRT use, recording playback and disk
   growth before changing Scrypted or adding Home Assistant.

MQTT is intentionally disabled for the first deployment. It will be added with
a dedicated broker account when the Home Assistant integration is introduced.
