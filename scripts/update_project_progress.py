"""Render the project overview from the evidence ledger; no application/network access."""
import argparse
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
    lines = ["# 项目进度总览", "", "> 本文件由 scripts/update_project_progress.py 从 PROJECT_PROGRESS.json 生成。修改台账后重新生成，勿直接修改本文件。", "", f"更新：{data['updated_at']} · iteration {data['current_iteration']} · 当前 {data['current_stage']}", "", "[总阶段路线图](PROJECT_MASTER_ROADMAP.md) · [维护规则](PROJECT_PROGRESS_MAINTENANCE.md)", "", f"**当前下一步：** {data['next_task']}", "", "全项目验收分母尚未冻结；以下显示阶段状态和证据闭环，不能推算全项目完成百分比。", "", "| 大阶段 | 当前状态 | 验收进度条 | " + " | ".join(LABELS) + " |", "| --- | --- | --- | " + " | ".join(["---"] * 5) + " |"]
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
    for name, content in (("PROJECT_PROGRESS.md", markdown),):
        path = directory / name
        if args.check:
            assert path.read_text(encoding="utf-8") == content, f"Stale view: {name}"
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Progress views {'verified' if args.check else 'updated'}: {len(data['stages'])} stages; release {passed}/{total} PASS; no overall percentage")


if __name__ == "__main__":
    main()
