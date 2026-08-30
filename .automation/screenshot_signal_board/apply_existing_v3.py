from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path.cwd()
BASE = ROOT / ".automation" / "screenshot_signal_board" / "apply_existing_v2.py"


def load_base():
    spec = importlib.util.spec_from_file_location("signal_board_apply_v2", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load apply_existing_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    module = load_base()
    module.main()
    router_path = ROOT / "backend/app/api/router.py"
    source = router_path.read_text(encoding="utf-8")
    # Match the existing repository's route convention rather than guessing
    # whether /api is set on APIRouter or include_router.
    existing_decorators = re.findall(r"@router\.(?:get|post|put|patch|delete)\(\s*['\"]([^'\"]+)", source)
    explicit_api = any(path.startswith("/api/") for path in existing_decorators if "industry-board" not in path and "signal-board" not in path)
    industry = "/api/industry-board" if explicit_api else "/industry-board"
    signal = "/api/signal-board" if explicit_api else "/signal-board"
    source = re.sub(
        r'@router\.get\("(?:/api)?/industry-board", tags=\["signal-board"\]\)',
        f'@router.get("{industry}", tags=["signal-board"])',
        source,
        count=1,
    )
    source = re.sub(
        r'@router\.get\("(?:/api)?/signal-board", tags=\["signal-board"\]\)',
        f'@router.get("{signal}", tags=["signal-board"])',
        source,
        count=1,
    )
    router_path.write_text(source, encoding="utf-8", newline="\n")
    module.update_manifest()


if __name__ == "__main__":
    main()
