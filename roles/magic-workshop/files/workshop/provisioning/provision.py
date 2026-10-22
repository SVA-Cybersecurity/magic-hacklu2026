#!/usr/bin/env python3
"""Provision workshop participants from participants.csv.

Run on the Docker host, from the repository root, with the stack already up:

    ./provisioning/provision.py apply
    ./provisioning/provision.py apply --only alice --dry-run
    ./provisioning/provision.py remove --only bob

For every participant this creates a Timesketch account and a sketch owned by
them, a JupyterHub (NativeAuthenticator) account, and a private data directory
holding a rendered MAGIC config.yaml and a pre-configured notebook.

Re-running is safe: accounts are updated in place and existing sketches reused.
"""

import argparse
import csv
import json
import os
import re
import secrets
import string
import subprocess
import sys
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "provisioning" / "templates"
GENERATED_CSV = ROOT / "participants.generated.csv"
GENERATED_FIELDS = [
    "username", "full_name", "email", "password", "sketch_id",
]

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")
PASSWORD_ALPHABET = string.ascii_letters + string.digits
# Seeding writes users_info directly, bypassing NativeAuthenticator's own
# checks, so enforce its policy here. Keep in sync with jupyterhub_config.py.
MIN_PASSWORD_LENGTH = 12
PASSWORD_LENGTH = 16

# Container uid/gid of the notebook image's `jovyan` user.
NB_UID, NB_GID = 1000, 100


class ProvisionError(Exception):
    pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        raise ProvisionError("No .env found. Run `make bootstrap` first.")
    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def run(cmd, env=None, capture=True):
    result = subprocess.run(
        cmd, cwd=ROOT, capture_output=capture, text=True, env=env
    )
    if result.returncode != 0:
        raise ProvisionError(
            f"command failed: {' '.join(cmd)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout


def gen_password():
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def render(template_name, mapping, json_escape=False):
    raw = (TEMPLATES / template_name).read_text()
    if json_escape:
        mapping = {k: json.dumps(str(v))[1:-1] for k, v in mapping.items()}
    return Template(raw).safe_substitute(mapping)


def read_participants(csv_path):
    if not csv_path.exists():
        raise ProvisionError(
            f"{csv_path} not found. Copy participants.csv.example and edit it."
        )
    participants = []
    with csv_path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            username = (row.get("username") or "").strip()
            if not username:
                continue
            if not USERNAME_RE.match(username):
                raise ProvisionError(
                    f"invalid username '{username}': must match {USERNAME_RE.pattern}"
                )
            password = (row.get("password") or "").strip()
            if not password:
                ts_password = (row.get("ts_password") or "").strip()
                jh_password = (row.get("jh_password") or "").strip()
                if ts_password and jh_password and ts_password != jh_password:
                    raise ProvisionError(
                        f"{username}: legacy Timesketch and JupyterHub passwords "
                        "differ; replace them with one password column."
                    )
                password = ts_password or jh_password
            if password and len(password) < MIN_PASSWORD_LENGTH:
                raise ProvisionError(
                    f"{username}: password is {len(password)} characters, "
                    f"minimum is {MIN_PASSWORD_LENGTH}. "
                    "Leave the column empty to generate a strong one."
                )
            participants.append(
                {
                    "username": username,
                    "full_name": (row.get("full_name") or username).strip(),
                    "email": (row.get("email") or "").strip(),
                    "password": password,
                }
            )
    if not participants:
        raise ProvisionError(f"{csv_path} contains no participants")
    return participants


def read_generated():
    """Previously issued credentials, keyed by username."""
    if not GENERATED_CSV.exists():
        return {}
    with GENERATED_CSV.open(newline="") as fh:
        rows = {}
        for row in csv.DictReader(fh):
            row["password"] = (
                row.get("password")
                or row.get("ts_password")
                or row.get("jh_password")
                or ""
            )
            rows[row["username"]] = row
        return rows


def read_provisioned():
    """Participants to act on for `remove`.

    Sourced from the generated credentials rather than participants.csv, so a
    participant can still be removed after being deleted from the input CSV.
    """
    generated = read_generated()
    if not generated:
        raise ProvisionError(f"{GENERATED_CSV} not found or empty; nothing to remove")
    return [generated[username] for username in sorted(generated)]


def write_generated(rows_by_username):
    with GENERATED_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=GENERATED_FIELDS)
        writer.writeheader()
        for username in sorted(rows_by_username):
            row = rows_by_username[username]
            writer.writerow({k: row.get(k, "") for k in GENERATED_FIELDS})
    os.chmod(GENERATED_CSV, 0o600)


def chown_tree(path):
    try:
        for item in [path, *path.rglob("*")]:
            os.chown(item, NB_UID, NB_GID)
    except PermissionError:
        print(f"  note: could not chown {path} to {NB_UID}:{NB_GID}")


# --------------------------------------------------------------------------
# provisioning steps
# --------------------------------------------------------------------------


def create_timesketch_user(username, password):
    run(
        [
            "docker", "compose", "exec", "-T", "timesketch-web",
            "tsctl", "create-user", username, "--password", password,
        ]
    )
    # create-user does not reactivate an account previously disabled by `remove`.
    run(
        [
            "docker", "compose", "exec", "-T", "timesketch-web",
            "tsctl", "enable-user", username,
        ]
    )


def create_sketch(env, username, password, sketch_name):
    docker_env = {**os.environ, "PARTICIPANT_PASSWORD": password}
    out = run(
        [
            "docker", "run", "--rm",
            "--network", env["DOCKER_NETWORK_NAME"],
            "-e", "PARTICIPANT_PASSWORD",
            "-v", f"{ROOT / 'provisioning'}:/srv/provisioning:ro",
            "--entrypoint", "/opt/conda/bin/python3",
            env["SINGLEUSER_IMAGE"],
            "/srv/provisioning/create_sketch.py",
            "--host", "http://timesketch-web:5000",
            "--username", username,
            "--name", sketch_name,
            "--description", f"Workshop sketch for {username}",
        ],
        env=docker_env,
    )
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if not lines or not lines[-1].isdigit():
        raise ProvisionError(f"could not parse sketch id from: {out!r}")
    return int(lines[-1])


def write_participant_data(env, participant, sketch_id, sketch_name):
    user_dir = ROOT / env["PARTICIPANT_DATA_DIR"] / participant["username"]
    (user_dir / "output").mkdir(parents=True, exist_ok=True)
    (user_dir / "logs").mkdir(parents=True, exist_ok=True)

    public_url = f"https://{env['PUBLIC_HOSTNAME']}"
    mapping = {
        "USERNAME": participant["username"],
        "FULL_NAME": participant["full_name"],
        "EMAIL": participant["email"],
        "TS_USERNAME": participant["username"],
        "PASSWORD": participant["password"],
        "SKETCH_ID": sketch_id,
        "SKETCH_NAME": sketch_name,
        "TIMESKETCH_HOST_URI": "http://timesketch-web:5000",
        "PUBLIC_URL": public_url,
        "MAGIC_CLIENT_ID": env.get("MAGIC_CLIENT_ID", ""),
        "MAGIC_CLIENT_SECRET": env.get("MAGIC_CLIENT_SECRET", ""),
        "MAGIC_TENANT_ID": env.get("MAGIC_TENANT_ID", ""),
    }

    (user_dir / "config.yaml").write_text(
        render("magic-config.yaml.tmpl", mapping)
    )
    (user_dir / ".timesketchrc").write_text(render("timesketchrc.tmpl", mapping))
    (user_dir / "Workshop-Getting-Started.ipynb").write_text(
        render("workshop.ipynb.tmpl", mapping, json_escape=True)
    )
    (user_dir / "README.md").write_text(render("handout.md.tmpl", mapping))

    os.chmod(user_dir / "config.yaml", 0o600)
    os.chmod(user_dir / ".timesketchrc", 0o600)
    chown_tree(user_dir)

    handout_dir = ROOT / "handout"
    handout_dir.mkdir(exist_ok=True)
    handout = handout_dir / f"{participant['username']}.md"
    handout.write_text(render("handout.md.tmpl", mapping))
    os.chmod(handout, 0o600)


def seed_jupyterhub_user(participant):
    cmd = [
        "docker", "compose", "exec", "-T", "jupyterhub",
        "python3", "/srv/provisioning/seed_jupyterhub_users.py", "add",
        "--username", participant["username"],
        "--password", participant["password"],
    ]
    if participant["email"]:
        cmd += ["--email", participant["email"]]
    run(cmd)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_apply(args, env, participants):
    generated = read_generated()

    for participant in participants:
        username = participant["username"]
        print(f"[{username}]")

        previous = {} if args.rotate_passwords else generated.get(username, {})
        password = (
            participant["password"]
            or previous.get("password")
            or previous.get("ts_password")
            or previous.get("jh_password")
            or gen_password()
        )
        participant["password"] = password
        sketch_name = f"Workshop - {participant['full_name']}"

        if args.dry_run:
            print("  would create Timesketch user, sketch, data dir and hub account")
            continue

        print("  timesketch user")
        create_timesketch_user(username, participant["password"])

        print("  sketch")
        sketch_id = create_sketch(
            env, username, participant["password"], sketch_name
        )

        print(f"  data directory (sketch {sketch_id})")
        write_participant_data(env, participant, sketch_id, sketch_name)

        print("  jupyterhub account")
        seed_jupyterhub_user(participant)

        participant["sketch_id"] = sketch_id
        generated[username] = participant

    if args.dry_run:
        return

    write_generated(generated)

    print(f"\nProvisioned {len(participants)} participant(s).")
    print(f"Credentials: {GENERATED_CSV} and handout/<username>.md (both mode 0600).")
    print("No restart needed — participants can log in immediately.")


def cmd_remove(args, env, participants):
    for participant in participants:
        username = participant["username"]
        print(f"[{username}]")

        if args.dry_run:
            print("  would disable Timesketch user, drop hub account, archive data")
            continue

        run([
            "docker", "compose", "exec", "-T", "timesketch-web",
            "tsctl", "disable-user", username,
        ])
        run([
            "docker", "compose", "exec", "-T", "jupyterhub",
            "python3", "/srv/provisioning/seed_jupyterhub_users.py", "remove",
            "--username", username,
        ])
        subprocess.run(
            ["docker", "rm", "-f", f"workshop-nb-{username}"],
            cwd=ROOT, capture_output=True, text=True,
        )

        user_dir = ROOT / env["PARTICIPANT_DATA_DIR"] / username
        if user_dir.exists():
            archive = user_dir.with_name(f"{username}.removed")
            if archive.exists():
                print(f"  data already archived at {archive}, leaving {user_dir}")
            else:
                user_dir.rename(archive)
                print(f"  data archived to {archive}")

        handout = ROOT / "handout" / f"{username}.md"
        if handout.exists():
            handout.unlink()

    if args.dry_run:
        return

    generated = read_generated()
    for participant in participants:
        generated.pop(participant["username"], None)
    write_generated(generated)

    print("\nRemoved. Participant data was archived, not deleted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["apply", "remove"], nargs="?", default="apply"
    )
    parser.add_argument("--csv", type=Path, default=ROOT / "participants.csv")
    parser.add_argument(
        "--only", action="append", default=[],
        help="Limit to these usernames (repeatable)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--rotate-passwords", action="store_true",
        help="Issue new passwords instead of reusing previously generated ones",
    )
    args = parser.parse_args()

    try:
        env = load_env()
        if args.action == "apply":
            participants = read_participants(args.csv)
            source = args.csv
        else:
            participants = read_provisioned()
            source = GENERATED_CSV

        if args.only:
            wanted = set(args.only)
            participants = [p for p in participants if p["username"] in wanted]
            missing = wanted - {p["username"] for p in participants}
            if missing:
                raise ProvisionError(f"not in {source}: {', '.join(sorted(missing))}")

        if args.action == "apply":
            cmd_apply(args, env, participants)
        else:
            cmd_remove(args, env, participants)
    except ProvisionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
