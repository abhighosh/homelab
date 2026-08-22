#!/bin/bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

readonly RULE_PATH=/etc/udev/rules.d/70-intel-arc-a310-render.rules
readonly RULE='SUBSYSTEM=="drm", KERNEL=="renderD*", ATTRS{vendor}=="0x8086", ATTRS{device}=="0x56a6", SYMLINK+="dri/arc-a310-render"'

printf '%s\n' "${RULE}" > "${RULE_PATH}"
chmod 0644 "${RULE_PATH}"
udevadm control --reload-rules
udevadm trigger --subsystem-match=drm --action=add
udevadm settle

if [[ ! -e /dev/dri/arc-a310-render ]]; then
  echo "Arc render alias was not created." >&2
  exit 1
fi

resolved=$(readlink -f /dev/dri/arc-a310-render)
vendor=$(cat "/sys/class/drm/$(basename "${resolved}")/device/vendor")
device=$(cat "/sys/class/drm/$(basename "${resolved}")/device/device")

if [[ ${vendor} != 0x8086 || ${device} != 0x56a6 ]]; then
  echo "Alias resolved to unexpected device ${vendor}:${device}." >&2
  exit 1
fi

echo "Arc A310 render alias ready: /dev/dri/arc-a310-render -> ${resolved}"
