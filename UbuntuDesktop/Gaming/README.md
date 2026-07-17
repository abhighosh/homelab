# Gaming session

Host-level configuration for the restricted `gaming` account on
`ubuntu-desktop`.

The account is deliberately separate from the administrative `abhi` account.
It must not receive sudo, Docker access, development credentials, or access to
`/home/abhi`.

Run `setup-steam-autostart` with sudo to install the GNOME autostart entry that
starts Steam silently when `gaming` logs in. Steam and Big Picture preferences,
controller layouts, login tokens, and other per-user runtime state remain on
the host and do not belong in this repository.

