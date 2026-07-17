#!/bin/sh
set -eu

# Compose secrets and Git-backed config are deliberately read-only. Copy them
# into the container filesystem so Mosquitto can enforce its expected private
# ownership and permissions without changing files in the repository.
cp /config-source/mosquitto.conf /mosquitto/config/mosquitto.conf
cp /config-source/acl /mosquitto/config/acl
cp /run/secrets/mosquitto_passwords /mosquitto/config/passwords
chown mosquitto:mosquitto \
  /mosquitto/config/mosquitto.conf \
  /mosquitto/config/acl \
  /mosquitto/config/passwords
chmod 0700 \
  /mosquitto/config/mosquitto.conf \
  /mosquitto/config/acl \
  /mosquitto/config/passwords

exec /docker-entrypoint.sh mosquitto -c /mosquitto/config/mosquitto.conf
