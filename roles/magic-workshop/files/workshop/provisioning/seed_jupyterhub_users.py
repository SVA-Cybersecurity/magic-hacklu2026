#!/usr/bin/env python3
"""Seed NativeAuthenticator accounts for workshop participants.

Runs INSIDE the jupyterhub container, invoked by provisioning/provision.py on
the host. Writes directly to NativeAuthenticator's `users_info` table because
the /hub/signup endpoint is disabled on purpose (see jupyterhub_config.py).
"""

import argparse
import os
import sys

import bcrypt
from jupyterhub.orm import new_session_factory
from nativeauthenticator.orm import UserInfo

DB_URL = os.environ.get(
    "JUPYTERHUB_DB_URL", "sqlite:////srv/jupyterhub/data/jupyterhub.sqlite"
)


def _session():
    return new_session_factory(DB_URL)()


def add_user(username, password, email=None):
    db = _session()
    try:
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        info = db.query(UserInfo).filter(UserInfo.username == username).first()
        if info is None:
            db.add(
                UserInfo(
                    username=username,
                    password=hashed,
                    is_authorized=True,
                    email=email or None,
                )
            )
            action = "created"
        else:
            info.password = hashed
            info.is_authorized = True
            if email:
                info.email = email
            action = "updated"
        db.commit()
    finally:
        db.close()
    print(f"{action} {username}")


def remove_user(username):
    db = _session()
    try:
        info = db.query(UserInfo).filter(UserInfo.username == username).first()
        if info is None:
            print(f"absent {username}")
            return
        db.delete(info)
        db.commit()
        print(f"removed {username}")
    finally:
        db.close()


def list_users():
    db = _session()
    try:
        for info in db.query(UserInfo).order_by(UserInfo.username).all():
            print(f"{info.username}\tauthorized={info.is_authorized}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    add = sub.add_parser("add", help="Create or update an account")
    add.add_argument("--username", required=True)
    add.add_argument("--password", required=True)
    add.add_argument("--email", default=None)

    rm = sub.add_parser("remove", help="Delete an account")
    rm.add_argument("--username", required=True)

    sub.add_parser("list", help="List accounts")

    args = parser.parse_args()
    if args.action == "add":
        add_user(args.username, args.password, args.email)
    elif args.action == "remove":
        remove_user(args.username)
    else:
        list_users()
    return 0


if __name__ == "__main__":
    sys.exit(main())
