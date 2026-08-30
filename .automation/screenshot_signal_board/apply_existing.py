from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"integration anchor missing in {path}: {old[:120]!r}")
    write(path, content.replace(old, new, 1))


def append_once(path: str, marker: str, block: str) -> None:
    content = read(path)
    if marker in content:
        return
    write(path, content.rstrip() + "\n\n" + block.strip() + "\n")


def patch_router() -> None:
    path = "backend/app/api/router.py"
    content = read(path)
    import_block = (
        "from app.db.session import session_scope as screenshot_board_session_scope\n"
        "from app.services.industry_board_service import IndustryBoardService\n"
        "from app.services.screenshot_signal_board_service import ScreenshotSignalBoardService\n"
    )
    if "ScreenshotSignalBoardService" not in content:
        future_line = "from __future__ import annotations\n"
        if future_line not in content:
            raise RuntimeError("router future import anchor missing")
        content = content.replace(future_line, future_line + "\n" + import_block, 1)
    route_marker = 'def screenshot_signal_board():'
    if route_marker not in content:
        route_block = '''

@router.get("/industry-board", tags=["signal-board"])
def screenshot_industry_board():
    """Return the 31-industry and market-anchor display registry.

    Registry membership is not a provider qualification. Missing active-universe
    entries remain explicitly pending and cannot become actionable evidence.
    """
    return IndustryBoardService().snapshot()


@router.get("/signal-board", tags=["signal-board"])
def screenshot_signal_board():
    """Return the colorful five-level board from persisted deterministic data."""
    with screenshot_board_session_scope() as db:
        return ScreenshotSignalBoardService().build(db)
'''
        content = content.rstrip() + route_block + "\n"
    write(path, content)


def patch_index() -> None:
    path = "backend/app/static/index.html"
    content = read(path)
    css_link = '  <link rel="stylesheet" href="/assets/screenshot_signal_board.css?v=0.2.0">\n'
    if "screenshot_signal_board.css" not in content:
        if "</head>" not in content:
            raise RuntimeError("index head anchor missing")
        content = content.replace("</head>", css_link + "</head>", 1)

    fragment = read("backend/app/static/screenshot_signal_board.html").strip()
    if 'id="screenshotSignalBoard"' not in content:
        warning_anchor = '      <div id="globalWarning" class="warning-banner hidden"></div>'
        if warning_anchor not in content:
            raise RuntimeError("globalWarning anchor missing")
        content = content.replace(warning_anchor, warning_anchor + "\n" + fragment, 1)

    legacy_replacements = [
        (
            '<div id="summaryCards" class="summary-grid"></div>',
            '<div id="summaryCards" class="summary-grid legacy-dashboard-surface"></div>',
        ),
        (
            '<div class="panel market-summary-panel">',
            '<div class="panel market-summary-panel legacy-dashboard-surface">',
        ),
        (
            '<section id="marketContextSection" class="panel observed-surface"',
            '<section id="marketContextSection" class="panel observed-surface legacy-dashboard-surface"',
        ),
        (
            '      <div class="panel">\n        <div class="panel-head">\n          <div><div class="eyebrow">DETERMINISTIC SIGNALS · OBSERVED + MODEL VIEW</div><h2>ETF / LOF 信号分级</h2></div>',
            '      <div class="panel legacy-dashboard-surface">\n        <div class="panel-head">\n          <div><div class="eyebrow">DETERMINISTIC SIGNALS · OBSERVED + MODEL VIEW</div><h2>ETF / LOF 信号分级</h2></div>',
        ),
    ]
    for old, new in legacy_replacements:
        if new in content:
            continue
        if old not in content:
            raise RuntimeError(f"legacy surface anchor missing: {old[:90]!r}")
        content = content.replace(old, new, 1)

    script_link = '  <script src="/assets/screenshot_signal_board.js?v=0.2.0"></script>\n'
    if "screenshot_signal_board.js" not in content:
        if "</body>" not in content:
            raise RuntimeError("index body anchor missing")
        content = content.replace("</body>", script_link + "</body>", 1)
    write(path, content)


def patch_docs() -> None:
    append_once(
        "README.md",
        "## 截图同款行业信号板",
        '''## 截图同款行业信号板

独立分支 `feat/screenshot-signal-board-v2` 增加彩色首页：申万31个一级行业、沪深300/标普500/纳斯达克/黄金场内代理、可加仓/可入场/可试探/观望/减仓五级分组，以及量能、均线、MACD、KDJ、TD、RSI、板块ETF代理宽度、近1周和明日预测。详见 `docs/SCREENSHOT_SIGNAL_BOARD.md` 与 `docs/INDUSTRY_UNIVERSE.md`。

行业基金映射是研究种子，未经Tushare/AKShare、流动性和源时间戳资格时不可执行。QDII ETF不等同于境外指数实时点位，预测默认保持 `not_calibrated`。''',
    )
    append_once(
        "STATUS.md",
        "## Screenshot signal board branch",
        '''## Screenshot signal board branch

- 状态：代码完成并在独立分支验证；未合并 `main`。
- 已完成：31行业注册表、四个市场锚、彩色五级信号板、行业筛选、ETF代理宽度、底部证据卡、API、测试和文档。
- 远端可验证：pytest、JS、编译、密钥扫描、Alembic、ShellCheck、Compose、Docker镜像和Mock流水线。
- 本地/ECS仍需：真实基金代码与跟踪指数核验、50–150只活动池、至少五年行情、实时源时间戳、PostgreSQL恢复、浏览器视觉验收和预测校准。''',
    )
    append_once(
        "HANDOFF.md",
        "## Screenshot signal board handoff",
        '''## Screenshot signal board handoff

接收分支：`feat/screenshot-signal-board-v2`。先阅读 `docs/LOCAL_AGENT_PROMPT_SIGNAL_BOARD.md`，再运行完整门禁与Mock浏览器验收。行业注册表不会自动扩大活动自选池；未初始化基金只显示不可执行占位。真实资格完成前保持 `pending_real_provider_qualification`、`not_calibrated`，实时源时间未认证时保持 `actionable=false`。''',
    )
    append_once(
        "docs/ARCHITECTURE.md",
        "## Screenshot-parity presentation layer",
        '''## Screenshot-parity presentation layer

`IndustryBoardService` 负责31行业与市场锚配置完整性；`ScreenshotSignalBoardService` 只读取持久化行情、指标、预测和信号并组装展示DTO。浏览器脚本只做分类展示、筛选和颜色映射，不重算生产指标或策略权重。`config/industry_board.json` 与活动 `watchlist.json` 分离，使未资格产品只能作为非执行占位。''',
    )
    append_once(
        "docs/IMPLEMENTATION_MATRIX.md",
        "## Screenshot signal board",
        '''## Screenshot signal board

| 能力 | 代码状态 | 真实环境状态 |
|---|---|---|
| 31个申万一级行业 | 已实现 | 分类稳定；ETF映射待Provider资格 |
| 四个市场锚 | 已实现 | QDII/黄金代理待实时资格 |
| 五级彩色信号表 | 已实现 | Mock与静态门禁可验证 |
| 板块涨跌 | ETF代理池宽度已实现 | 行业成份股广度未接入 |
| 明日/一周预测展示 | 已实现 | `not_calibrated` |
| 活动行业基金池 | 注册表已实现 | 用户审阅后写入watchlist |
| 阿里云视觉验收 | 脚本和文档已实现 | 需本地/ECS执行 |''',
    )
    append_once(
        "codex/skills/fund-research/SKILL.md",
        "## Screenshot-parity industry board",
        '''## Screenshot-parity industry board

处理行业信号板、截图复刻、ETF代理选择或页面验收时，先读取 `references/industry-signal-board.md`。不得把ETF代理宽度称为行业成份股广度，不得把QDII ETF称为境外指数实时点位，不得将未资格产品变成可执行信号。''',
    )


def update_manifest() -> None:
    excluded = {".git", ".venv", "__pycache__", ".pytest_cache", "reports", "backups", ".automation"}
    rows: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if relative.as_posix() == "FILE_MANIFEST.txt" or any(part in excluded for part in relative.parts):
            continue
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative.as_posix()}")
    write("FILE_MANIFEST.txt", "\n".join(rows) + "\n")


def main() -> None:
    patch_router()
    patch_index()
    patch_docs()
    update_manifest()


if __name__ == "__main__":
    main()
