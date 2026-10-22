#!/usr/bin/env bash
# Enable (or disable) HTTP basic auth in front of nginx.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

AUTH_CONF=config/nginx/auth.conf
HTPASSWD=config/nginx/htpasswd

if [[ "${1:-}" == "--disable" ]]; then
  cat > "${AUTH_CONF}" <<'EOF'
# Default: no HTTP basic auth in front of the apps.
# Run `make htpasswd USER=... ` to enable it, `make no-htpasswd` to disable.
auth_basic off;
EOF
  echo "* basic auth disabled — run 'make restart-nginx' to apply"
  exit 0
fi

USER_NAME="${1:-}"
PASSWORD="${2:-}"
[[ -n "${USER_NAME}" ]] || { echo "usage: $0 <username> [password] | --disable" >&2; exit 1; }

if [[ -z "${PASSWORD}" ]]; then
  read -r -s -p "Password for '${USER_NAME}': " PASSWORD; echo
fi

HASH="$(openssl passwd -apr1 "${PASSWORD}")"
touch "${HTPASSWD}"
# Replace any existing entry for this user.
grep -v "^${USER_NAME}:" "${HTPASSWD}" > "${HTPASSWD}.tmp" 2>/dev/null || true
mv "${HTPASSWD}.tmp" "${HTPASSWD}"
echo "${USER_NAME}:${HASH}" >> "${HTPASSWD}"

cat > "${AUTH_CONF}" <<'EOF'
auth_basic           "MAGIC Workshop";
auth_basic_user_file /etc/nginx/htpasswd;
EOF

echo "* basic auth enabled for '${USER_NAME}' — run 'make restart-nginx' to apply"
