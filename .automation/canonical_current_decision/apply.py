from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"patch anchor missing in {path}: {old[:120]!r}")
    write(path, content.replace(old, new, 1))


def patch_signal_center() -> None:
    path = "backend/app/services/signal_center_service.py"
    replace_once(
        path,
        "from app.services.holding_service import HoldingService\nfrom app.utils.numbers import clamp, finite_or_none, percentile_rank\n",
        "from app.services.holding_service import HoldingService\n"
        "from app.services.signal_grade_service import SignalGradeService\n"
        "from app.utils.current_decision import resolve_current_decision, summarize_sources\n"
        "from app.utils.numbers import clamp, finite_or_none, percentile_rank\n",
    )
    replace_once(
        path,
        "        decision_snapshot_id, decision_rows = self._latest_decision_rows(db)\n\n"
        "        rows: list[dict[str, Any]] = []\n",
        "        decision_snapshot_id, decision_rows = self._latest_decision_rows(db)\n"
        "        missing_grade_codes = {\n"
        "            str(instrument.ts_code).strip().upper()\n"
        "            for instrument in instruments\n"
        "            if not (decision_rows.get(str(instrument.ts_code).strip().upper()) or {}).get(\"grade\")\n"
        "        }\n"
        "        grade_payload = SignalGradeService(self.settings).build(db) if missing_grade_codes else {}\n"
        "        fallback_grades = {\n"
        "            str(row.get(\"ts_code\") or \"\").strip().upper(): row\n"
        "            for row in grade_payload.get(\"rows\", [])\n"
        "            if str(row.get(\"ts_code\") or \"\").strip().upper() in missing_grade_codes\n"
        "        }\n\n"
        "        rows: list[dict[str, Any]] = []\n",
    )
    replace_once(
        path,
        "            signal = latest_signals.get(instrument.id)\n"
        "            if signal is None:\n"
        "                continue\n"
        "            indicator = latest_indicators.get(instrument.id)\n"
        "            values = indicator.values_json if indicator else {}\n"
        "            effective = round(float(signal.score or 0) * coefficient, 2)\n"
        "            decision_row = decision_rows.get(instrument.ts_code)\n"
        "            current_state = (\n"
        "                str(decision_row.get(\"grade\"))\n"
        "                if decision_row and decision_row.get(\"grade\")\n"
        "                else signal.state\n"
        "            )\n"
        "            categories = self._categories(\n"
        "                current_state,\n"
        "                effective,\n"
        "                values,\n"
        "                coefficient,\n"
        "                canonical=decision_row is not None,\n"
        "            )\n",
        "            signal = latest_signals.get(instrument.id)\n"
        "            indicator = latest_indicators.get(instrument.id)\n"
        "            values = indicator.values_json if indicator else {}\n"
        "            effective = round(float(signal.score or 0) * coefficient, 2) if signal is not None else 0.0\n"
        "            code = str(instrument.ts_code).strip().upper()\n"
        "            decision_row = decision_rows.get(code)\n"
        "            fallback_grade = fallback_grades.get(code)\n"
        "            resolved = resolve_current_decision(\n"
        "                decision_board_grade=(decision_row or {}).get(\"grade\"),\n"
        "                signal_grade_fallback=(fallback_grade or {}).get(\"grade\"),\n"
        "                production_signal_state=signal.state if signal is not None else None,\n"
        "            )\n"
        "            if resolved is None:\n"
        "                continue\n"
        "            current_state = resolved.state\n"
        "            categories = self._categories(\n"
        "                current_state,\n"
        "                effective,\n"
        "                values,\n"
        "                coefficient,\n"
        "                canonical=resolved.canonical,\n"
        "            )\n",
    )
    replace_once(
        path,
        "                    \"current_state\": current_state,\n"
        "                    \"decision_row\": decision_row,\n"
        "                    \"categories\": categories,\n",
        "                    \"current_state\": current_state,\n"
        "                    \"current_state_source\": resolved.source,\n"
        "                    \"current_state_canonical\": resolved.canonical,\n"
        "                    \"decision_row\": decision_row,\n"
        "                    \"fallback_grade\": fallback_grade,\n"
        "                    \"categories\": categories,\n",
    )
    replace_once(
        path,
        "        summary = {\n"
        "            \"total\": len(rows),\n"
        "            \"opportunity\": sum(1 for row in rows if \"opportunity\" in row[\"categories\"]),\n"
        "            \"risk\": sum(1 for row in rows if \"risk\" in row[\"categories\"]),\n"
        "            \"take_profit\": sum(1 for row in rows if \"take_profit\" in row[\"categories\"]),\n"
        "        }\n"
        "        return {\n",
        "        summary = {\n"
        "            \"total\": len(rows),\n"
        "            \"opportunity\": sum(1 for row in rows if \"opportunity\" in row[\"categories\"]),\n"
        "            \"risk\": sum(1 for row in rows if \"risk\" in row[\"categories\"]),\n"
        "            \"take_profit\": sum(1 for row in rows if \"take_profit\" in row[\"categories\"]),\n"
        "        }\n"
        "        current_states = {\n"
        "            row[\"instrument\"].ts_code: {\n"
        "                \"state\": row[\"current_state\"],\n"
        "                \"source\": row[\"current_state_source\"],\n"
        "                \"canonical\": row[\"current_state_canonical\"],\n"
        "                \"decision_board_grade\": (row.get(\"decision_row\") or {}).get(\"grade\"),\n"
        "                \"signal_grade_fallback\": (row.get(\"fallback_grade\") or {}).get(\"grade\"),\n"
        "                \"production_signal_state\": row[\"signal\"].state if row.get(\"signal\") is not None else None,\n"
        "            }\n"
        "            for row in rows\n"
        "        }\n"
        "        source_counts: dict[str, int] = {}\n"
        "        for row in rows:\n"
        "            source = row[\"current_state_source\"]\n"
        "            source_counts[source] = source_counts.get(source, 0) + 1\n"
        "        current_state_source = summarize_sources([row[\"current_state_source\"] for row in rows])\n"
        "        return {\n",
    )
    replace_once(
        path,
        "            \"current_state_source\": \"decision_board_snapshot\" if decision_rows else \"signal_snapshot_fallback\",\n"
        "            \"decision_snapshot_id\": decision_snapshot_id,\n"
        "            \"curve_basis\": \"historical_signal_snapshots\",\n",
        "            \"current_state_source\": current_state_source,\n"
        "            \"current_state_source_counts\": source_counts,\n"
        "            \"current_states\": current_states,\n"
        "            \"signal_grade_fallback_version\": grade_payload.get(\"version\"),\n"
        "            \"coefficient_semantics\": \"ranking_and_take_profit_only_when_current_state_is_canonical\",\n"
        "            \"decision_snapshot_id\": decision_snapshot_id,\n"
        "            \"curve_basis\": \"historical_signal_snapshots_legacy\",\n",
    )
    replace_once(
        path,
        "    def _opportunity_key(row: dict[str, Any]) -> tuple[float, float]:\n"
        "        return (-row[\"effective\"], -float(row[\"signal\"].score or 0))\n",
        "    def _opportunity_key(row: dict[str, Any]) -> tuple[float, float]:\n"
        "        signal = row.get(\"signal\")\n"
        "        signal_score = float(signal.score or 0) if signal is not None else 0.0\n"
        "        return (-row[\"effective\"], -signal_score)\n",
    )
    replace_once(
        path,
        "        signal: SignalSnapshot = row[\"signal\"]\n",
        "        signal: SignalSnapshot | None = row[\"signal\"]\n",
    )
    replace_once(
        path,
        "            \"state\": row[\"current_state\"],\n"
        "            \"production_signal_state\": signal.state,\n"
        "            \"decision_board_grade\": (row[\"decision_row\"] or {}).get(\"grade\"),\n"
        "            \"score\": round(float(signal.score or 0), 2),\n"
        "            \"effective_score\": row[\"effective\"],\n"
        "            \"confidence\": round(float(signal.confidence or 0), 2),\n"
        "            \"is_actionable\": bool(signal.is_actionable),\n",
        "            \"state\": row[\"current_state\"],\n"
        "            \"state_source\": row[\"current_state_source\"],\n"
        "            \"state_canonical\": row[\"current_state_canonical\"],\n"
        "            \"production_signal_state\": signal.state if signal is not None else None,\n"
        "            \"decision_board_grade\": (row[\"decision_row\"] or {}).get(\"grade\"),\n"
        "            \"signal_grade_fallback\": (row.get(\"fallback_grade\") or {}).get(\"grade\"),\n"
        "            \"score\": round(float(signal.score or 0), 2) if signal is not None else 0.0,\n"
        "            \"effective_score\": row[\"effective\"],\n"
        "            \"confidence\": round(float(signal.confidence or 0), 2) if signal is not None else 0.0,\n"
        "            \"is_actionable\": bool(signal.is_actionable) if signal is not None else False,\n",
    )
    replace_once(
        path,
        "            \"signal_time\": signal.as_of_time,\n"
        "            \"expires_at\": signal.expires_at,\n",
        "            \"signal_time\": signal.as_of_time if signal is not None else None,\n"
        "            \"expires_at\": signal.expires_at if signal is not None else None,\n",
    )


def patch_tests() -> None:
    path = "backend/tests/test_signal_center.py"
    replace_once(path, "from sqlalchemy import select\n", "from sqlalchemy import delete, select\n")
    replace_once(
        path,
        "from app.services.signal_center_service import (\n"
        "    OPPORTUNITY_STATES,\n"
        "    RISK_STATES,\n"
        "    SignalCenterService,\n"
        ")\n",
        "from app.services.signal_center_service import (\n"
        "    OPPORTUNITY_STATES,\n"
        "    RISK_STATES,\n"
        "    SignalCenterService,\n"
        ")\n"
        "from app.utils.current_decision import DECISION_BOARD_SOURCE, MIXED_SOURCE, SIGNAL_GRADE_SOURCE\n",
    )
    replace_once(
        path,
        "    assert payload[\"current_state_source\"] == \"decision_board_snapshot\"\n"
        "    assert payload[\"decision_snapshot_id\"] == snapshot_id\n",
        "    assert payload[\"current_state_source\"] == MIXED_SOURCE\n"
        "    assert payload[\"decision_snapshot_id\"] == snapshot_id\n"
        "    assert payload[\"current_states\"][instrument.ts_code][\"source\"] == DECISION_BOARD_SOURCE\n"
        "    assert payload[\"current_states\"][instrument.ts_code][\"canonical\"] is True\n",
    )
    content = read(path)
    marker = "def test_signal_grade_fallback_is_canonical_without_decision_snapshot"
    if marker not in content:
        content = content.rstrip() + "\n\n\n" + '''def test_signal_grade_fallback_is_canonical_without_decision_snapshot(bootstrapped, db_session):
    db_session.execute(delete(DecisionBoardSnapshot))
    db_session.flush()

    payload = SignalCenterService().build(db_session, coefficient=1.5)

    assert payload["current_state_source"] == SIGNAL_GRADE_SOURCE
    assert payload["current_state_source_counts"][SIGNAL_GRADE_SOURCE] == payload["summary"]["total"]
    assert payload["signal_grade_fallback_version"].startswith("signal-grade-")
    assert payload["current_states"]
    assert all(item["source"] == SIGNAL_GRADE_SOURCE for item in payload["current_states"].values())
    assert all(item["canonical"] is True for item in payload["current_states"].values())

    low = SignalCenterService().build(db_session, coefficient=0.5)
    high = SignalCenterService().build(db_session, coefficient=1.5)
    assert low["summary"]["opportunity"] == high["summary"]["opportunity"]
    assert low["summary"]["risk"] == high["summary"]["risk"]
'''
        write(path, content)


def patch_config() -> None:
    replace_once(
        "config/strategy.json",
        '  "signal_center_version": "signal-center-v0.2.0",\n',
        '  "signal_center_version": "signal-center-v0.3.0-canonical-fallback",\n',
    )


def patch_docs() -> None:
    path = "docs/REFERENCE_BOARD_PARITY.md"
    replace_once(
        path,
        "`DecisionBoardSnapshot.rows[].grade` 是当前展示的 canonical conclusion。\n\n"
        "`SignalCenterService` 的机会/风险/止盈前排只是排序和解释视图：\n",
        "当前结论按**每只 ETF**解析，优先级固定为：\n\n"
        "1. 最新 `DecisionBoardSnapshot.rows[].grade`；\n"
        "2. 该 ETF 在决策快照中缺失时，回退 `SignalGradeService` 当前五档；\n"
        "3. 两者均无时才使用 `SignalSnapshot.state`，且只作为最后审计兼容值。\n\n"
        "前两者属于 canonical conclusion；第三层不是。部分快照会显式标记 `mixed_per_instrument`，不能假装所有标的来自同一来源。\n\n"
        "`SignalCenterService` 的机会/风险/止盈前排只是排序和解释视图：\n",
    )
    replace_once(
        path,
        "- `state`: 当前 canonical grade；\n"
        "- `production_signal_state`: 原 SignalSnapshot 状态；\n"
        "- `decision_board_grade`: 决策看板 grade；\n"
        "- `current_state_source`: `decision_board_snapshot` 或无快照时的 `signal_snapshot_fallback`。\n",
        "- `state`: 当前解析后的状态；\n"
        "- `state_source` / `state_canonical`: 单 ETF 的来源与 canonical 标记；\n"
        "- `production_signal_state`: 原 SignalSnapshot 状态；\n"
        "- `decision_board_grade`: 决策看板 grade；\n"
        "- `signal_grade_fallback`: 缺失快照行时的确定性五档；\n"
        "- `current_state_source`: 全部同源时返回具体来源；部分标的来源不同则为 `mixed_per_instrument`。\n",
    )


def main() -> None:
    patch_signal_center()
    patch_tests()
    patch_config()
    patch_docs()


if __name__ == "__main__":
    main()
