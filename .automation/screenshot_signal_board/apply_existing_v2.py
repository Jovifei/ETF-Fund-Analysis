from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8", newline="\n")


def append_once(path: str, marker: str, block: str) -> None:
    content = read(path)
    if marker not in content:
        write(path, content.rstrip() + "\n\n" + block.strip() + "\n")


def patch_router() -> None:
    path = "backend/app/api/router.py"
    content = read(path)
    imports = (
        "from app.db.session import session_scope as screenshot_board_session_scope\n"
        "from app.services.industry_board_service import IndustryBoardService\n"
        "from app.services.screenshot_signal_board_service import ScreenshotSignalBoardService\n"
    )
    if "ScreenshotSignalBoardService" not in content:
        match = re.search(r"^from __future__ import annotations\s*$", content, flags=re.M)
        if not match:
            raise RuntimeError("router.py 缺少 future import")
        insert = match.end()
        content = content[:insert] + "\n\n" + imports.rstrip() + content[insert:]
    if "def screenshot_signal_board():" not in content:
        prefixed = bool(re.search(r"APIRouter\s*\([^\n]*prefix\s*=\s*['\"]/?api['\"]", content))
        industry_path = "/industry-board" if prefixed else "/api/industry-board"
        signal_path = "/signal-board" if prefixed else "/api/signal-board"
        content = content.rstrip() + f'''


@router.get("{industry_path}", tags=["signal-board"])
def screenshot_industry_board():
    """Return the 31-industry and market-anchor display registry."""
    return IndustryBoardService().snapshot()


@router.get("{signal_path}", tags=["signal-board"])
def screenshot_signal_board():
    """Build the five-level display board from persisted deterministic evidence."""
    with screenshot_board_session_scope() as db:
        return ScreenshotSignalBoardService().build(db)
'''
    write(path, content + "\n")


def add_class(content: str, element_pattern: str, class_name: str) -> str:
    pattern = re.compile(element_pattern, re.S)
    match = pattern.search(content)
    if not match:
        return content
    tag = match.group(0)
    if class_name in tag:
        return content
    class_match = re.search(r'class="([^"]*)"', tag)
    if class_match:
        replacement = tag[: class_match.start(1)] + class_match.group(1) + " " + class_name + tag[class_match.end(1) :]
    else:
        replacement = tag[:-1] + f' class="{class_name}">'
    return content[: match.start()] + replacement + content[match.end() :]


def patch_index() -> None:
    path = "backend/app/static/index.html"
    content = read(path)
    if "screenshot_signal_board.css" not in content:
        content = content.replace(
            "</head>",
            '  <link rel="stylesheet" href="/assets/screenshot_signal_board.css?v=0.2.0">\n</head>',
            1,
        )
    if 'id="screenshotSignalBoard"' not in content:
        fragment = read("backend/app/static/screenshot_signal_board.html").strip()
        warning = re.search(r'<div\s+id="globalWarning"[^>]*></div>', content)
        if warning:
            content = content[: warning.end()] + "\n" + fragment + content[warning.end() :]
        else:
            dashboard = re.search(r'<section\s+id="view-dashboard"[^>]*>', content)
            if not dashboard:
                raise RuntimeError("index.html 缺少 dashboard 容器")
            content = content[: dashboard.end()] + "\n" + fragment + content[dashboard.end() :]
    content = add_class(content, r'<div\s+id="summaryCards"[^>]*>', "legacy-dashboard-surface")
    content = add_class(content, r'<div\s+class="[^"]*market-summary-panel[^"]*"[^>]*>', "legacy-dashboard-surface")
    content = add_class(content, r'<section\s+id="marketContextSection"[^>]*>', "legacy-dashboard-surface")
    legacy_signal = re.search(
        r'<div\s+class="panel">(?=\s*<div\s+class="panel-head">.*?DETERMINISTIC SIGNALS)',
        content,
        flags=re.S,
    )
    if legacy_signal and "legacy-dashboard-surface" not in legacy_signal.group(0):
        content = content[: legacy_signal.start()] + '<div class="panel legacy-dashboard-surface">' + content[legacy_signal.end() :]
    if "screenshot_signal_board.js" not in content:
        content = content.replace(
            "</body>",
            '  <script src="/assets/screenshot_signal_board.js?v=0.2.0"></script>\n</body>',
            1,
        )
    write(path, content)


def patch_docs() -> None:
    append_once(
        "README.md",
        "## 截图同款行业信号板",
        '''## 截图同款行业信号板

分支 `feat/screenshot-signal-board-v2` 增加彩色首页：申万31个一级行业、沪深300/标普500/纳斯达克/黄金场内代理、五级信号分组，以及量能、均线、MACD、KDJ、TD、RSI、ETF代理宽度、近1周和明日预测。详见 `docs/SCREENSHOT_SIGNAL_BOARD.md`、`docs/INDUSTRY_UNIVERSE.md` 和 `docs/SIGNAL_BOARD_RUNBOOK.md`。

行业基金映射是研究种子；未经真实Provider、流动性和源时间戳资格时不可执行。QDII ETF不等同于境外指数实时点位，预测默认保持 `not_calibrated`。''',
    )
    append_once(
        "STATUS.md",
        "## Screenshot signal board branch",
        '''## Screenshot signal board branch

- 独立分支：`feat/screenshot-signal-board-v2`，未合并 `main`。
- 已实现：31行业注册表、四个市场锚、彩色五级信号表、行业筛选、ETF代理宽度、底部证据卡、API、测试和文档。
- 远端门禁：pytest、JS、编译、密钥扫描、Alembic、ShellCheck、Compose、镜像和Mock流水线。
- 本地/ECS仍需：真实基金/跟踪指数核验、活动池、历史行情、实时源时间戳、PostgreSQL恢复、视觉验收和预测校准。''',
    )
    append_once(
        "HANDOFF.md",
        "## Screenshot signal board handoff",
        '''## Screenshot signal board handoff

接收分支 `feat/screenshot-signal-board-v2` 后，阅读 `docs/LOCAL_AGENT_PROMPT_SIGNAL_BOARD.md` 并运行完整门禁与Mock视觉验收。行业注册表不会自动扩大活动自选池；未初始化基金只显示不可执行占位。真实资格完成前保持 `pending_real_provider_qualification`、`not_calibrated`，源时间未认证时保持 `actionable=false`。''',
    )
    append_once(
        "docs/ARCHITECTURE.md",
        "## Screenshot-parity presentation layer",
        '''## Screenshot-parity presentation layer

`IndustryBoardService` 校验31行业与四个市场锚；`ScreenshotSignalBoardService` 只读取持久化行情、指标、预测和信号并组装展示DTO。浏览器只做筛选、分组和颜色映射，不重算生产指标或权重。行业注册表与活动 `watchlist.json` 分离，未资格产品只能成为非执行占位。''',
    )
    append_once(
        "docs/IMPLEMENTATION_MATRIX.md",
        "## Screenshot signal board",
        '''## Screenshot signal board

| 能力 | 代码状态 | 真实环境状态 |
|---|---|---|
| 31个申万一级行业 | 已实现 | ETF映射待Provider资格 |
| 四个市场锚 | 已实现 | QDII/黄金代理待实时资格 |
| 五级彩色信号表 | 已实现 | Mock与静态门禁可验证 |
| 板块涨跌 | ETF代理池宽度已实现 | 行业成份股广度未接入 |
| 明日/一周预测展示 | 已实现 | `not_calibrated` |
| 活动行业基金池 | 注册表已实现 | 用户审阅后写入watchlist |
| 阿里云视觉验收 | 文档已实现 | 需本地/ECS执行 |''',
    )
    append_once(
        "codex/skills/fund-research/SKILL.md",
        "## Screenshot-parity industry board",
        '''## Screenshot-parity industry board

处理行业信号板、截图复刻、ETF代理选择或页面验收时，先读取 `references/industry-signal-board.md`。不得把ETF代理宽度称为行业成份股广度，不得把QDII ETF称为境外指数实时点位，不得将未资格产品变成可执行信号。''',
    )


def update_manifest() -> None:
    excluded = {".git", ".venv", "__pycache__", ".pytest_cache", "reports", "backups", ".automation"}
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if rel.as_posix() == "FILE_MANIFEST.txt" or any(part in excluded for part in rel.parts):
            continue
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel.as_posix()}")
    write("FILE_MANIFEST.txt", "\n".join(rows) + "\n")


def main() -> None:
    patch_router()
    patch_index()
    patch_docs()
    update_manifest()


if __name__ == "__main__":
    main()
