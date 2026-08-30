from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path.cwd()
BASE = ROOT / ".automation" / "screenshot_signal_board" / "apply_existing_v3.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_if_present(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old in text:
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> None:
    integration = load_module(BASE, "signal_board_apply_v3")
    integration.main()

    industry = ROOT / "backend/app/services/industry_board_service.py"
    replace_if_present(
        industry,
        '        config_dir = Path(getattr(self.settings, "config_dir", "config"))\n'
        '        self.path = config_dir / "industry_board.json"\n',
        '        configured_dir = getattr(self.settings, "config_dir", None)\n'
        '        if configured_dir:\n'
        '            config_dir = Path(configured_dir)\n'
        '        else:\n'
        '            strategy_path = Path(getattr(self.settings, "strategy_config_path", "config/strategy.json"))\n'
        '            config_dir = strategy_path.parent\n'
        '        self.path = config_dir / "industry_board.json"\n',
    )

    board_service = ROOT / "backend/app/services/screenshot_signal_board_service.py"
    text = board_service.read_text(encoding="utf-8")
    text = text.replace(
        '            values = _json_value(getattr(indicator, "values", None), {}) if indicator else {}\n',
        '            values = (\n'
        '                _json_value(\n'
        '                    getattr(indicator, "values", None)\n'
        '                    or getattr(indicator, "values_json", None),\n'
        '                    {},\n'
        '                )\n'
        '                if indicator\n'
        '                else {}\n'
        '            )\n',
    )
    text = text.replace(
        '            score = _float(getattr(signal, "score", None)) if signal else None\n'
        '            previous_score = _float(getattr(previous, "score", None)) if previous else None\n',
        '            score = _float(\n'
        '                getattr(signal, "score", None)\n'
        '                if signal is not None\n'
        '                else None\n'
        '            )\n'
        '            if score is None and signal is not None:\n'
        '                score = _float(getattr(signal, "signal_score", None))\n'
        '            previous_score = _float(\n'
        '                getattr(previous, "score", None)\n'
        '                if previous is not None\n'
        '                else None\n'
        '            )\n'
        '            if previous_score is None and previous is not None:\n'
        '                previous_score = _float(getattr(previous, "signal_score", None))\n',
    )
    text = text.replace(
        '                    "kind": getattr(instrument, "kind", None),\n',
        '                    "kind": str(getattr(instrument, "kind", "") or ""),\n',
    )
    board_service.write_text(text, encoding="utf-8", newline="\n")

    script = ROOT / "backend/app/static/screenshot_signal_board.js"
    js = script.read_text(encoding="utf-8")
    js = js.replace(
        "      <td><span class=\"metric-main ${rsiClass}\">${escapeHtml(rsi)}</span><span class=\"metric-sub\">${numberValue(values.rsi14) >= 72 ? '超买' : numberValue(values.rsi14) < 38 ? '偏弱' : '趋势中段'}</span></td>",
        "      <td><span class=\"metric-main ${rsiClass}\">${escapeHtml(rsi)}</span><span class=\"metric-sub\">${numberValue(values.rsi14) === null ? '待数据' : numberValue(values.rsi14) >= 72 ? '超买' : numberValue(values.rsi14) < 38 ? '偏弱' : '趋势中段'}</span></td>",
    )
    js = js.replace(
        "<span>明日 <b class=\"${percentClass((numberValue(forecast?.expected_return) || 0) * 100)}\">${forecast ? percent(numberValue(forecast.expected_return) * 100) : '—'}</b></span>",
        "<span>明日 <b class=\"${percentClass(numberValue(forecast?.expected_return) === null ? null : numberValue(forecast.expected_return) * 100)}\">${numberValue(forecast?.expected_return) === null ? '—' : percent(numberValue(forecast.expected_return) * 100)}</b></span>",
    )
    script.write_text(js, encoding="utf-8", newline="\n")

    # Ensure the two routes follow the repository's existing /api convention.
    router = ROOT / "backend/app/api/router.py"
    source = router.read_text(encoding="utf-8")
    existing = [
        item
        for item in re.findall(r"@router\.(?:get|post|put|patch|delete)\(\s*['\"]([^'\"]+)", source)
        if "industry-board" not in item and "signal-board" not in item
    ]
    explicit_api = any(item.startswith("/api/") for item in existing)
    industry_path = "/api/industry-board" if explicit_api else "/industry-board"
    signal_path = "/api/signal-board" if explicit_api else "/signal-board"
    source = re.sub(
        r'@router\.get\("(?:/api)?/industry-board", tags=\["signal-board"\]\)',
        f'@router.get("{industry_path}", tags=["signal-board"])',
        source,
        count=1,
    )
    source = re.sub(
        r'@router\.get\("(?:/api)?/signal-board", tags=\["signal-board"\]\)',
        f'@router.get("{signal_path}", tags=["signal-board"])',
        source,
        count=1,
    )
    router.write_text(source, encoding="utf-8", newline="\n")
    integration_v2 = load_module(
        ROOT / ".automation" / "screenshot_signal_board" / "apply_existing_v2.py",
        "signal_board_apply_v2_for_manifest",
    )
    integration_v2.update_manifest()


if __name__ == "__main__":
    main()
