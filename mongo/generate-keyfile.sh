#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
secret_dir="$repo_root/secrets"
keyfile="$secret_dir/mongo-keyfile"

mkdir -p "$secret_dir"
if [ -f "$keyfile" ]; then
  echo "MongoDB keyfile already exists: $keyfile"
  exit 0
fi

openssl rand -base64 756 > "$keyfile"
chmod 600 "$keyfile"
echo "Generated MongoDB keyfile: $keyfile"

