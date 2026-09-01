#!/usr/bin/env python3
from __future__ import annotations

import secrets

print(f"AUTH_SESSION_SECRET={secrets.token_urlsafe(48)}")
print(f"POSTGRES_PASSWORD={secrets.token_urlsafe(36).replace('-', 'A').replace('_', 'b')}")
