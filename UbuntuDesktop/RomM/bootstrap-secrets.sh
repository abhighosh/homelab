#!/usr/bin/env bash
set -Eeuo pipefail

base=${ROMM_BASE_PATH:-/home/abhi/Docker/RomM}
data=${ROMM_DATA_PATH:-$base/data}
secrets=${ROMM_SECRETS_PATH:-$base/secrets}
rotate=false
if [[ ${1:-} == "--rotate" ]]; then
    rotate=true
elif (( $# != 0 )); then
    echo "Usage: $0 [--rotate]" >&2
    exit 1
fi

umask 077
install -d -m 0700 "$secrets"
install -d -m 0750 \
    "$data/resources" \
    "$data/assets" \
    "$data/config" \
    "$data/redis" \
    "$data/mariadb"

if [[ $rotate == false && ( -e "$secrets/romm.env" || -e "$secrets/mariadb.env" ) ]]; then
    echo "Refusing to replace existing RomM secret files in $secrets." >&2
    exit 1
fi

db_password=$(openssl rand -hex 32)
root_password=$(openssl rand -hex 32)
auth_secret=$(openssl rand -hex 32)

cat >"$secrets/romm.env" <<EOF
DB_PASSWD=$db_password
ROMM_AUTH_SECRET_KEY=$auth_secret
EOF

cat >"$secrets/mariadb.env" <<EOF
MARIADB_ROOT_PASSWORD=$root_password
MARIADB_DATABASE=romm
MARIADB_USER=romm
MARIADB_PASSWORD=$db_password
EOF

chmod 0600 "$secrets/romm.env" "$secrets/mariadb.env"
echo "RomM runtime directories and secrets are ready below $base."
