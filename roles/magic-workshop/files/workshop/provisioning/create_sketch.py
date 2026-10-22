#!/usr/bin/env python3
"""Create (or find) a participant's Timesketch sketch and print its id.

Runs inside a throwaway container built from the singleuser image, which is
the only image in the stack that ships timesketch-api-client. Authenticates as
the participant so the sketch is owned by them and no ACL grant is needed.

Only the sketch id goes to stdout; everything else goes to stderr.
"""

import argparse
import os
import sys

from timesketch_api_client import client as ts_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", default="")
    args = parser.parse_args()

    password = os.environ.get("PARTICIPANT_PASSWORD")
    if not password:
        print("PARTICIPANT_PASSWORD is not set", file=sys.stderr)
        return 1

    api = ts_client.TimesketchApi(
        host_uri=args.host,
        username=args.username,
        password=password,
        verify=False,
    )

    for sketch in api.list_sketches(per_page=1000, scope="user"):
        if sketch.name == args.name:
            print(f"reusing existing sketch {sketch.id}", file=sys.stderr)
            print(sketch.id)
            return 0

    sketch = api.create_sketch(name=args.name, description=args.description)
    print(f"created sketch {sketch.id}", file=sys.stderr)
    print(sketch.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
