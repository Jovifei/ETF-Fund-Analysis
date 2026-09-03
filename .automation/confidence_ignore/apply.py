from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"patch anchor missing in {path}: {old!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> None:
    replace_once(
        "backend/app/static/decision_board_workbuddy.js",
        "function confidenceBand(value){if(!numeric(value))return '未验证';const n=Number(value);return n>=60?'可参考':n>=40?'弱信号':'低参考';}",
        "function confidenceBand(value){if(!numeric(value))return '未验证';const n=Number(value);return n>=60?'可参考':n>=40?'弱信号':'忽略';}",
    )
    replace_once(
        "backend/app/static/decision_board_workbuddy.html",
        "<div><b>conf&lt;40</b><span>方向接近随机 · 低参考价值</span></div>",
        "<div><b>conf&lt;40</b><span>涨跌接近随机 · 基本忽略</span></div>",
    )
    replace_once(
        "backend/app/static/decision_board_workbuddy.test.js",
        "test('confidence interpretation matches reference bands',()=>{const ui=load();assert.equal(ui.confidenceBand(66),'可参考');assert.equal(ui.confidenceBand(48),'弱信号');assert.equal(ui.confidenceBand(28),'低参考');});",
        "test('confidence interpretation matches reference bands',()=>{const ui=load();assert.equal(ui.confidenceBand(66),'可参考');assert.equal(ui.confidenceBand(48),'弱信号');assert.equal(ui.confidenceBand(28),'忽略');assert.equal(ui.confidenceBand(40),'弱信号');assert.equal(ui.confidenceBand(39),'忽略');});",
    )
    replace_once(
        "docs/REFERENCE_BOARD_PARITY.md",
        "- conf < 40：低参考价值。",
        "- conf < 40：涨跌接近随机，基本忽略。",
    )


if __name__ == "__main__":
    main()
