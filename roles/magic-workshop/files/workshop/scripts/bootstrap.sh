#!/usr/bin/env bash
# One-time host preparation: .env, directories, stock Timesketch config files.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$(pwd)"

FORCE_CONFIG=0
[[ "${1:-}" == "--force-timesketch-config" ]] && FORCE_CONFIG=1

rand() { LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "${1:-32}"; }

command -v docker >/dev/null || { echo "ERROR: docker is not installed." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERROR: docker compose plugin missing." >&2; exit 1; }

# --- .env -------------------------------------------------------------------
if [[ -f .env ]]; then
  echo "* .env already exists, keeping it"
else
  cp env.example .env
  sed -i "s#^WORKSHOP_ROOT=.*#WORKSHOP_ROOT=${ROOT}#" .env
  sed -i "s#^POSTGRES_PASSWORD=.*#POSTGRES_PASSWORD=$(rand 32)#" .env
  sed -i "s#^TIMESKETCH_ADMIN_PASSWORD=.*#TIMESKETCH_ADMIN_PASSWORD=$(rand 24)#" .env
  echo "* created .env (edit MAGIC_* and PUBLIC_HOSTNAME before continuing)"
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ "${WORKSHOP_ROOT}" != "${ROOT}" ]]; then
  echo "WARNING: WORKSHOP_ROOT=${WORKSHOP_ROOT} but this checkout is ${ROOT}." >&2
  echo "         DockerSpawner bind mounts will break unless this is fixed." >&2
fi

# --- directories ------------------------------------------------------------
mkdir -p \
  data/opensearch data/postgresql \
  logs upload certs handout \
  "${PARTICIPANT_DATA_DIR}" \
  config/timesketch/sigma/rules \
  config/timesketch/llm_summarize \
  config/timesketch/llm_starred_events_report \
  config/timesketch/nl2q

mkdir -p "${SHARED_DATA_DIR:-shared-data}"
chmod 0755 "${SHARED_DATA_DIR:-shared-data}"

touch config/nginx/htpasswd

# OpenSearch runs as uid 1000; TAKE_FILE_OWNERSHIP also handles this at runtime.
chown 1000 data/opensearch 2>/dev/null || \
  echo "  (could not chown data/opensearch — run: sudo chown 1000 ${ROOT}/data/opensearch)"

echo "* directories ready"

# --- stock Timesketch config ------------------------------------------------
if [[ -f config/timesketch/timesketch.conf && "${FORCE_CONFIG}" -eq 0 ]]; then
  echo "* Timesketch config already present, skipping download"
else
  BASE="https://raw.githubusercontent.com/google/timesketch/${TIMESKETCH_CONFIG_REF}"
  fetch() { curl -fsSL "${BASE}/$1" -o "config/timesketch/$2"; }

  echo -n "* fetching Timesketch config files.."
  fetch data/timesketch.conf                    timesketch.conf
  fetch data/tags.yaml                          tags.yaml
  fetch data/plaso.mappings                     plaso.mappings
  fetch data/generic.mappings                   generic.mappings
  fetch data/regex_features.yaml                regex_features.yaml
  fetch data/winevt_features.yaml               winevt_features.yaml
  fetch data/ontology.yaml                      ontology.yaml
  fetch data/intelligence_tag_metadata.yaml     intelligence_tag_metadata.yaml
  fetch data/sigma_config.yaml                  sigma_config.yaml
  fetch data/sigma/rules/lnx_susp_zmap.yml      sigma/rules/lnx_susp_zmap.yml
  fetch data/plaso_formatters.yaml              plaso_formatters.yaml
  fetch data/context_links.yaml                 context_links.yaml
  fetch data/llm_summarize/prompt.txt           llm_summarize/prompt.txt
  fetch data/llm_starred_events_report/prompt.txt llm_starred_events_report/prompt.txt
  fetch data/nl2q/data_types.csv                nl2q/data_types.csv
  fetch data/nl2q/prompt_nl2q                   nl2q/prompt_nl2q
  fetch data/nl2q/examples_nl2q                 nl2q/examples_nl2q
  echo "OK"

  CONF=config/timesketch/timesketch.conf
  sed -i "s#SECRET_KEY = \"<KEY_GOES_HERE>\"#SECRET_KEY = \"$(rand 32)\"#" "${CONF}"
  sed -i "s#^UPLOAD_ENABLED = False#UPLOAD_ENABLED = True#" "${CONF}"
  sed -i "s#^UPLOAD_FOLDER = \"/tmp\"#UPLOAD_FOLDER = \"/usr/share/timesketch/upload\"#" "${CONF}"
  sed -i "s#^CELERY_BROKER_URL =.*#CELERY_BROKER_URL = \"redis://redis:6379\"#" "${CONF}"
  sed -i "s#^CELERY_RESULT_BACKEND =.*#CELERY_RESULT_BACKEND = \"redis://redis:6379\"#" "${CONF}"
  sed -i "s#postgresql://<USERNAME>:<PASSWORD>@localhost#postgresql://timesketch:${POSTGRES_PASSWORD}@postgres:5432#" "${CONF}"
  echo "* patched ${CONF}"
fi

# --- host kernel setting ----------------------------------------------------
CURRENT_MAX_MAP="$(sysctl -n vm.max_map_count 2>/dev/null || echo 0)"
if [[ "${CURRENT_MAX_MAP}" -lt 262144 ]]; then
  echo
  echo "ACTION REQUIRED: OpenSearch needs vm.max_map_count >= 262144 (currently ${CURRENT_MAX_MAP})."
  echo "  sudo sysctl -w vm.max_map_count=262144"
  echo "  echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf"
fi

echo
echo "Bootstrap done. Next:"
echo "  1. edit .env (PUBLIC_HOSTNAME, MAGIC_CLIENT_ID/SECRET/TENANT_ID)"
echo "  2. make certs"
echo "  3. make build && make up"
