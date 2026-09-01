#!/usr/bin/env python3
"""Print a pwdlib-recommended Argon2id password hash without echoing the password."""

from __future__ import annotations

import getpass

from pwdlib import PasswordHash


def main() -> int:
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not password or password != confirmation:
        return 1
    print(PasswordHash.recommended().hash(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
