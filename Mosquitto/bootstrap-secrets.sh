#!/bin/sh
set -eu

base_dir="${MOSQUITTO_RUNTIME_PATH:-/home/abhi/Docker/Mosquitto}"
secret_dir="$base_dir/secrets"
data_dir="$base_dir/data"

umask 077
mkdir -p "$secret_dir" "$data_dir"

for account in frigate homeassistant healthcheck; do
  password_file="$secret_dir/${account}_password"
  if [ ! -s "$password_file" ]; then
    openssl rand -base64 36 > "$password_file"
  fi
done

password_db="$secret_dir/passwords"
{
  printf 'frigate:'
  tr -d '\n' < "$secret_dir/frigate_password"
  printf '\nhomeassistant:'
  tr -d '\n' < "$secret_dir/homeassistant_password"
  printf '\nhealthcheck:'
  tr -d '\n' < "$secret_dir/healthcheck_password"
  printf '\n'
} > "$password_db"
chmod 700 "$password_db"

# Upgrade the temporary plaintext entries to Mosquitto's salted password
# hashes without putting any password in shell history or process arguments.
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$secret_dir:/work" \
  eclipse-mosquitto:2.0.22 \
  mosquitto_passwd -U /work/passwords

chmod 700 "$secret_dir"
chmod 600 "$secret_dir"/*_password
chmod 700 "$password_db"

printf '%s\n' "Mosquitto credentials created under $secret_dir."
printf '%s\n' "The plaintext client files are local secrets; the broker reads only a private copy of the hashed passwords file."
