# Gaming session

Host-level configuration for the restricted `gaming` account on
`ubuntu-desktop`.

The account is deliberately separate from the administrative `abhi` account.
It must not receive sudo, Docker access, development credentials, or access to
`/home/abhi`.

The host uses native GNOME Wayland and starts Steam in Big Picture mode when
`gaming` logs in. Steam and Big Picture preferences, controller layouts, login
tokens, and other per-user runtime state remain on the host and do not belong
in this repository.

## Controller desktop input on Wayland

Steam's desktop controller layout requests GNOME's Remote Desktop portal when
it injects mouse or keyboard input under Wayland. Current Steam clients do not
reliably preserve that permission when the controller reconnects.

`install-extest` installs a pinned build of
[Extest](https://github.com/Supreeeme/extest), a small XTEST compatibility
library that translates Steam's synthetic desktop input into a Linux `uinput`
device. The library is preloaded only into Steam through
`/usr/local/bin/steam-extest`; it is not a daemon and it is not globally
preloaded.

Run on `ubuntu-desktop`:

```console
sudo ./install-extest
```

The installer verifies the source archive checksum, builds the 32-bit library,
records its pinned upstream revision under `/usr/local/share/doc/extest`, and
installs the GNOME autostart entry. Ubuntu grants `/dev/uinput` access to the
active local session through a device ACL, so the `gaming` account does not
need permanent membership of the `input` group.

To disable Extest without uninstalling anything, change the autostart command
back to `/usr/games/steam -gamepadui`. To remove it, delete
`/usr/local/bin/steam-extest`, `/usr/local/lib/extest`, and
`/usr/local/share/doc/extest`, then rerun `setup-steam-autostart` after changing
its command.

## Console wake

`setup-console-wake` configures two independent wake paths and controller
recovery after resume:

- magic-packet Wake-on-LAN on `enp10s0` through native Netplan and
  NetworkManager settings;
- wake from the 8BitDo receiver below USB root hub `usb3`, using a narrow udev
  rule;
- a post-resume re-probe of USB device `3-1` when it matches the active 8BitDo
  receiver (`2dc8:3106`). Steam can otherwise miss the receiver because it
  changes from its idle identity while the graphical session is still
  resuming.

Run on `ubuntu-desktop`:

```console
sudo ./setup-console-wake
```

The Ethernet MAC address is `c8:7f:54:68:05:15`. The machine uses deep (S3)
suspend. Both controller wake and Wake-on-LAN should be tested after firmware,
kernel, or motherboard configuration changes. The re-probe waits three seconds
for resume to settle and does nothing if the controller is off or the expected
receiver is not present.

## Console session

The `gaming` account has no interactive password and is dedicated to the TV.
It must therefore never lock: a lock screen would make the console unusable
and inhibit Wayland capture. GNOME's blank-only state also prevents a new XDG
Portal capture session, so `setup-console-session` disables locking and
blanking, then suspends the complete machine after 15 idle minutes:

```console
sudo ./setup-console-session gaming
```

Sunshine's application hooks inhibit sleep throughout an active stream. Local
input keeps the GNOME session active during normal console use.

## Sunshine on native Wayland

Sunshine is installed as the system Flatpak. GNOME Wayland capture uses the
native XDG Desktop Portal and PipeWire path. The first launch requires choosing
the Samsung display and allowing remote interaction; GNOME stores the resulting
portal restore token in Sunshine's per-user state.

`setup-sunshine-host` installs the input rules, loads `uhid`, and enables the
vendor-provided service for the graphical session:

```console
sudo ./setup-sunshine-host gaming
```

Do not restore the old X11/NvFBC capture settings. The service starts only once
the graphical session exists, so the portal and the physical Wayland display
are available. Pairing credentials, certificates, restore tokens, and the
mutable Sunshine configuration are deliberately not stored in Git.

### Stream colour and suspend handling

Sunshine's Linux HDR support does not cover NVIDIA NVENC with GNOME's XDG
Desktop Portal. Capturing the HDR desktop into an SDR stream produces washed
out colours. Both Sunshine applications therefore call
`sunshine-stream-prepare` before streaming and `sunshine-stream-restore` after
disconnecting. The hooks temporarily select GNOME's `sdr-native` colour mode,
retain 3840x2160 at 119.88 Hz with VRR and 200% scale, and restore `bt2100`
afterward.

The prepare hook also creates a systemd sleep inhibitor for the duration of
the stream. The restore hook releases it even if the TV has disconnected and
HDR restoration fails. This allows normal idle suspension after streaming
without risking suspension during a quiet game or cutscene.

### Fullscreen capture reliability

Some fullscreen Vulkan applications, notably Eden, can enter GNOME direct
scanout. The TV continues to update, but portal-based streaming may receive a
stale composited frame. `setup-stream-compositor-guard` installs a minimal
GNOME Shell extension that disables direct scanout only while streaming:

```console
sudo ./setup-stream-compositor-guard gaming
```

For Sunshine, its existing application hooks update the guard when the stream
inhibitor starts and stops. For Steam Remote Play, an event-driven user service
watches for Steam's `steam-streaming-playback` PipeWire/Pulse sink. It enables
the guard when the sink appears and disables it after the session ends. There
is no polling, and direct scanout remains available for local gaming.
