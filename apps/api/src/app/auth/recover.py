from __future__ import annotations

import argparse
import getpass

from app.settings import get_settings

from .dependencies import build_auth_service
from .service import AuthError


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover an existing administrator account")
    parser.add_argument("username")
    args = parser.parse_args()
    first = getpass.getpass("Temporary password: ")
    second = getpass.getpass("Repeat temporary password: ")
    if first != second:
        raise SystemExit("Passwords do not match")
    try:
        build_auth_service(get_settings()).recover_existing_admin(args.username, first)
    except AuthError as error:
        raise SystemExit(error.code) from error
    print(f"Password reset for existing administrator {args.username}; change required at next login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
