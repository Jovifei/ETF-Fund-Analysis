#!/usr/bin/env python3
from __future__ import annotations

import json

from app.research.integrations import capability_matrix


if __name__ == "__main__":
    print(json.dumps({"integrations": capability_matrix()}, ensure_ascii=False, indent=2))
