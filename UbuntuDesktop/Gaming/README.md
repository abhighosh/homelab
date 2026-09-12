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
