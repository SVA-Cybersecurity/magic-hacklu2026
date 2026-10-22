#!/usr/bin/env bash
# Generate the self-signed certificate nginx serves.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

set -a
# shellcheck disable=SC1091
source .env
set +a

mkdir -p certs

if [[ -f certs/workshop.crt && "${1:-}" != "--force" ]]; then
  echo "certs/workshop.crt already exists (use 'make certs FORCE=--force' to replace)"
  exit 0
fi

if [[ "${PUBLIC_HOSTNAME}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  SAN="IP:${PUBLIC_HOSTNAME}"
else
  SAN="DNS:${PUBLIC_HOSTNAME}"
fi

openssl req -x509 -nodes -newkey rsa:4096 -days 825 \
  -keyout certs/workshop.key \
  -out certs/workshop.crt \
  -subj "/CN=${PUBLIC_HOSTNAME}/O=MAGIC Workshop" \
  -addext "subjectAltName=${SAN}" \
  -addext "basicConstraints=CA:FALSE" \
  -addext "keyUsage=digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth" 2>/dev/null

chmod 600 certs/workshop.key
echo "* self-signed certificate created for ${PUBLIC_HOSTNAME} (${SAN})"
openssl x509 -in certs/workshop.crt -noout -fingerprint -sha256
