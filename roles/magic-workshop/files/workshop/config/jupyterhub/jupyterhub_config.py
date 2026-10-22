"""JupyterHub configuration for the MAGIC workshop.

Participants are provisioned from participants.csv by provisioning/provision.py;
this file only reads the resulting allowed_users.json.
"""

import os
from pathlib import Path

import nativeauthenticator

c = get_config()  # noqa: F821

CONFIG_DIR = Path("/srv/jupyterhub/config")
DATA_DIR = Path("/srv/jupyterhub/data")

PARTICIPANT_DATA_HOST_PATH = os.environ["PARTICIPANT_DATA_HOST_PATH"]
SHARED_DATA_HOST_PATH = os.environ["SHARED_DATA_HOST_PATH"]


def _split_env(name):
    return {u.strip() for u in os.environ.get(name, "").split(",") if u.strip()}


# ---------------------------------------------------------------------------
# Hub
# ---------------------------------------------------------------------------
c.JupyterHub.bind_url = "http://0.0.0.0:8000/jupyter"
c.JupyterHub.hub_ip = "0.0.0.0"
# Spawned containers reach the hub by container name on the shared network.
c.JupyterHub.hub_connect_ip = "workshop-jupyterhub"
c.JupyterHub.db_url = f"sqlite:///{DATA_DIR}/jupyterhub.sqlite"
c.JupyterHub.cookie_secret_file = str(DATA_DIR / "jupyterhub_cookie_secret")
c.ConfigurableHTTPProxy.pid_file = str(DATA_DIR / "jupyterhub-proxy.pid")
c.JupyterHub.shutdown_on_logout = True
# Leave participant notebooks running across a hub restart.
c.JupyterHub.cleanup_servers = False

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
c.JupyterHub.authenticator_class = "native"
c.JupyterHub.template_paths = [
    f"{os.path.dirname(nativeauthenticator.__file__)}/templates/"
]

c.Authenticator.admin_users = _split_env("JUPYTERHUB_ADMIN_USERS")
# The real gate is NativeAuthenticator: authenticate() only succeeds for an
# existing, authorized row in users_info, and signup is disabled below, so the
# only way in is provisioning. Keeping allowed_users empty means adding a
# participant needs no hub restart (which would disrupt running notebooks).
c.Authenticator.allow_all = True

# Accounts are seeded by the provisioning script, so self-service signup is off.
c.NativeAuthenticator.enable_signup = False
c.NativeAuthenticator.open_signup = False
c.NativeAuthenticator.minimum_password_length = 12
c.NativeAuthenticator.check_common_password = True
c.NativeAuthenticator.allowed_failed_logins = 10
c.NativeAuthenticator.seconds_before_next_try = 300

# ---------------------------------------------------------------------------
# Spawner
# ---------------------------------------------------------------------------
c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"
c.DockerSpawner.image = os.environ["SINGLEUSER_IMAGE"]
c.DockerSpawner.network_name = os.environ["DOCKER_NETWORK_NAME"]
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.remove = True
c.DockerSpawner.pull_policy = "never"
c.DockerSpawner.name_template = "workshop-nb-{username}"
c.DockerSpawner.notebook_dir = "/home/jovyan/work"

def optional_env(name: str, default: str) -> str:
    """
    Liest eine optionale Umgebungsvariable.
    """
    return os.environ.get(name, default).strip()


shared_volume = optional_env(
    "/opt/magic-workshop/shared",
    "jupyterhub-shared",
)

c.DockerSpawner.volumes = {
    f"{PARTICIPANT_DATA_HOST_PATH}/{{username}}": "/home/jovyan/work",
    SHARED_DATA_HOST_PATH: {
        "bind": "/home/jovyan/work/shared",
        "mode": "ro",
    },
}

c.Spawner.default_url = "/lab"
c.Spawner.mem_limit = os.environ.get("SINGLEUSER_MEM_LIMIT", "3G")
c.Spawner.cpu_limit = float(os.environ.get("SINGLEUSER_CPU_LIMIT", "1.5"))
c.Spawner.start_timeout = 300
c.Spawner.http_timeout = 120

c.Spawner.environment = {
    "MAGIC_CLIENT_ID": os.environ.get("MAGIC_CLIENT_ID", ""),
    "MAGIC_CLIENT_SECRET": os.environ.get("MAGIC_CLIENT_SECRET", ""),
    "MAGIC_TENANT_ID": os.environ.get("MAGIC_TENANT_ID", ""),
    "TIMESKETCH_HOST_URI": os.environ.get(
        "TIMESKETCH_HOST_URI", "http://timesketch-web:5000"
    ),
    "WORKSHOP_PUBLIC_HOSTNAME": os.environ.get("PUBLIC_HOSTNAME", ""),
}


def fail_if_unprovisioned(spawner):
    """Give a readable error instead of an empty notebook when data is missing."""
    user_dir = Path(PARTICIPANT_DATA_HOST_PATH) / spawner.user.name
    if not user_dir.is_dir():
        raise RuntimeError(
            f"No workshop data directory for '{spawner.user.name}'. "
            "Run `make provision` on the host first."
        )


c.Spawner.pre_spawn_hook = fail_if_unprovisioned
