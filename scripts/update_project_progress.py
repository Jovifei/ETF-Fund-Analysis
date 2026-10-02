"""Render the project overview from the evidence ledger; no application/network access."""
import argparse
import html
import json
from pathlib import Path

FIELDS = ("code", "tests", "review", "deploy", "live")
LABELS = ("代码", "测试", "远端审核", "部署", "线上验收")
STATES = {"TODO", "IN_PROGRESS", "PASS", "BLOCKED", "REOPENED", "N/A", "待核对", "PENDING", "READY", "部分PASS"}


def validate(data):
    seen = set()
    assert len(data["stages"]) == 10, "Expected S0-S9"
    for stage in data["stages"]:
        assert stage["id"] not in seen, "Duplicate stage"
        seen.add(stage["id"])
        assert set(stage["dimensions"]) == set(FIELDS)
        assert all(v in STATES for v in stage["dimensions"].values())
        ids = set()
        for unit in stage["units"]:
            assert unit["id"] not in ids, "Duplicate unit"
            ids.add(unit["id"])
            assert set(unit["dimensions"]) == set(FIELDS)
            for field, status in unit["dimensions"].items():
                assert status in STATES, f"Invalid status: {unit['id']}"
                if status == "PASS":
                    assert unit["evidence"], f"PASS without evidence: {unit['id']}"
                if status == "N/A":
                    assert unit["na_reasons"].get(field), f"N/A without reason: {unit['id']}"
        if stage["counter_frozen"]:
            assert stage.get("freeze_evidence"), "Frozen denominator without plan evidence"
    assert seen == {f"S{i}" for i in range(10)}
    for gate in data["release_gates"]:
        assert gate["status"] in STATES
        if gate["status"] == "PASS":
            assert gate["evidence"], "Release PASS without evidence"


def complete(unit):
    return all(unit["dimensions"][f] in {"PASS", "N/A"} for f in FIELDS)


def counter(stage):
    if not stage["counter_frozen"]:
        return "待冻结 / 待证据映射"
    total = len(stage["units"])
    count = sum(complete(u) for u in stage["units"])
    filled = round(20 * count / total) if total else 0
    return f"{'█' * filled}{'░' * (20-filled)} {count}/{total}"


def clean(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="Fail if generated views are stale")
    args = parser.parse_args()
    directory = args.root / "docs"
    data = json.loads((directory / "PROJECT_PROGRESS.json").read_text(encoding="utf-8"))
    validate(data)
    passed = sum(g["status"] == "PASS" for g in data["release_gates"])
    total = len(data["release_gates"])
    filled = round(20 * passed / total)
    bar = f"{'█' * filled}{'░' * (20-filled)} {passed}/{total}"
    lines = ["# 项目进度总览", "", "> 本文件由 scripts/update_project_progress.py 从 PROJECT_PROGRESS.json 生成。修改台账后重新生成，勿直接修改本文件。", "", f"更新：{data['updated_at']} · iteration {data['current_iteration']} · 当前 {data['current_stage']}", "", "[总阶段路线图](PROJECT_MASTER_ROADMAP.md) · [图形进度板](PROJECT_PROGRESS.html) · [维护规则](PROJECT_PROGRESS_MAINTENANCE.md)", "", f"**当前下一步：** {data['next_task']}", "", "全项目验收分母尚未冻结；以下显示阶段状态和证据闭环，不能推算全项目完成百分比。", "", "| 大阶段 | 当前状态 | 验收进度条 | " + " | ".join(LABELS) + " |", "| --- | --- | --- | " + " | ".join(["---"] * 5) + " |"]
    for stage in data["stages"]:
        values = [f"{stage['id']} {stage['name']}", stage["status"], counter(stage)] + [stage["dimensions"][f] for f in FIELDS]
        lines.append("| " + " | ".join(map(clean, values)) + " |")
    release_title = data.get("release_counter_title", "当前发布验收清单")
    release_note = data.get("release_counter_note", "R9拆为平台与私有；READY不计PASS。这不是S3总功能完成率。")
    lines += ["", "## " + release_title, "", f"`{bar}` {release_note}", "", "| 检查 | 内容 | 状态 | 证据 |", "| --- | --- | --- | --- |"]
    for gate in data["release_gates"]:
        lines.append("| " + " | ".join(clean(gate[k]) for k in ("id", "name", "status", "evidence")) + " |")
    lines += ["", "## 版本与卡点", "", f"- 已部署代码：`{data['deployed_code_sha']}`；tree `{data['deployed_tree']}`。", f"- 历史发布证据基线：`{data['release_evidence_head']}`。最新总览文档提交查询：`{data['docs_commit_lookup']}`。", f"- Alembic：`{data['alembic']}`。", f"- 真实数据：{data['real_data']}；actionable={str(data['actionable']).lower()}；运行时激活={str(data['runtime_activated']).lower()}；自动交易={str(data['auto_trading']).lower()}。"]
    lines += ["- " + b for b in data["blockers"]]
    if data.get("current_evidence"):
        lines += ["", f"- 当前身份核验：[{data['production_status']}]({data['current_evidence']})；仅元数据核验，不替代完整发布验收。", f"- 镜像：`{data['image_config_digest']}`；决策板 `{data['read_model_version']}` / `{data['board_generated_at']}`。"]
    lines += ["", "## 阶段候选任务与五维状态", "", "以下任务来自总规划。分母未正式冻结，历史项未映射证据时保留待核对。代码侧PASS不替代真实线上验收；旧基线子任务的PASS不追认当前新版本。"]
    for stage in data["stages"]:
        lines += ["", f"### {stage['id']} {stage['name']}", "", f"旧编号：{stage['legacy']}。{stage['counter_note']}。", "", "| 子任务 | 内容 | " + " | ".join(LABELS) + " |", "| --- | --- | " + " | ".join(["---"] * 5) + " |"]
        for unit in stage["units"]:
            lines.append("| " + " | ".join(map(clean, [unit["id"], unit["name"]] + [unit["dimensions"][f] for f in FIELDS])) + " |")
    lines += ["", "## 变更记录", ""] + [f"- {event['date']} / iteration{event['iteration']}：{event['description']}" for event in data["events"]]
    markdown = "\n".join(lines) + "\n"
    esc = html.escape
    cards = []
    for stage in data["stages"]:
        rows = "".join("<tr>" + "".join(f"<td>{esc(str(v))}</td>" for v in [u["id"], u["name"]] + [u["dimensions"][f] for f in FIELDS]) + "</tr>" for u in stage["units"])
        progress = "<span>待冻结 / 待证据映射</span>"
        if stage["counter_frozen"]:
            done = sum(complete(u) for u in stage["units"])
            progress = f'<progress value="{done}" max="{len(stage["units"])}"></progress> {done}/{len(stage["units"])}'
        dimension_line = " · ".join(label + " " + stage["dimensions"][field] for field, label in zip(FIELDS, LABELS))
        cards.append(f'<section><h2>{esc(stage["id"] + " " + stage["name"])}</h2><p>{esc(stage["status"])}</p><p>{progress}</p><p>{esc(dimension_line)}</p><details><summary>展开子任务与状态</summary><div class="table"><table><thead><tr><th>子任务</th><th>内容</th>{"".join(f"<th>{label}</th>" for label in LABELS)}</tr></thead><tbody>{rows}</tbody></table></div></details></section>')
    release_rows = "".join(f'<tr><td>{esc(g["id"])}</td><td>{esc(g["name"])}</td><td>{esc(g["status"])}</td></tr>' for g in data["release_gates"])
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ETF项目进度总览</title><style>body{font:16px/1.65 system-ui;background:#f2f5fa;color:#172338;margin:0;padding:24px}main{max-width:1300px;margin:auto}header,section{background:white;border:1px solid #d9e1ed;border-radius:12px;padding:20px;margin:12px 0}h1{font-size:30px}h2{font-size:20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:12px}progress{width:100%;height:24px;accent-color:#176657}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border-bottom:1px solid #d9e1ed;text-align:left}summary{cursor:pointer}a{color:#1552a5}@media(max-width:600px){body{padding:12px}.grid{grid-template-columns:1fr}}</style><main>'
    page += f'<header><h1>ETF / LOF 项目进度</h1><p>更新 {esc(data["updated_at"])} · 当前 {esc(data["current_stage"])} · 接力iteration {data["current_iteration"]}</p><p>{esc(data["next_task"])}</p><p>已部署代码 {esc(data["deployed_code_sha"])} · Alembic {esc(data["alembic"])}</p><p>全项目分母未冻结，不显示整体百分比；代码、测试、审核、部署与线上验收分别记录。</p><a href="PROJECT_MASTER_ROADMAP.md">完整总路线图</a> · <a href="PROJECT_PROGRESS_MAINTENANCE.md">维护规则</a><h2>{esc(release_title)}：{passed}/{total} PASS</h2><progress value="{passed}" max="{total}" aria-label="发布清单历史进度"></progress><p>{esc(release_note)}</p><details><summary>发布检查历史与当前卡点</summary><table>{release_rows}</table><p>{esc("；".join(data["blockers"]))}</p></details></header><div class="grid">' + "".join(cards) + "</div></main></html>\n"
    for name, content in (("PROJECT_PROGRESS.md", markdown), ("PROJECT_PROGRESS.html", page)):
        path = directory / name
        if args.check:
            assert path.read_text(encoding="utf-8") == content, f"Stale view: {name}"
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Progress views {'verified' if args.check else 'updated'}: {len(data['stages'])} stages; release {passed}/{total} PASS; no overall percentage")


if __name__ == "__main__":
    main()
