"""Embed the existing WorkBuddy report, not a second market page or renderer."""
from pathlib import Path

from starlette.responses import HTMLResponse

STATIC = Path(__file__).resolve().parents[1] / "static"


def original_board_frame():
    html = (STATIC / "decision_board_workbuddy.html").read_text(encoding="utf-8")
    # The original report markup is a single source of truth. Fail loudly if
    # its boundaries change rather than silently serving another login/shell.
    start, stop = '<main class="report-shell">', '</main>'
    if html.count(start) != 1 or html.count(stop) != 1:
        raise RuntimeError("original_board_template_boundary_changed")
    report = html[html.index(start):html.index(stop) + len(stop)]
    return HTMLResponse(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>ETF 决策快照</title>'
        '<link rel="stylesheet" href="/assets/decision_board_workbuddy.css">'
        '<link rel="stylesheet" href="/assets/decision_board_embed.css">'
        '</head><body data-workspace-embed="true">'
        '<span id="connectionBadge" hidden></span>' + report +
        '<script src="/assets/decision_board_workbuddy.js"></script>'
        '<script src="/assets/decision_board_embed.js"></script></body></html>',
        headers={"Cache-Control": "private, no-store"},
    )
