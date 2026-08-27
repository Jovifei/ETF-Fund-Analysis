#!/usr/bin/env python3
from __future__ import annotations

import secrets

print(f"PRIVATE_ACCESS_TOKEN={secrets.token_urlsafe(40)}")
print(f"POSTGRES_PASSWORD={secrets.token_urlsafe(36).replace('-', 'A').replace('_', 'b')}")
