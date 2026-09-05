"""Industry/concept board research view (ETF proxies, not East Money scrape)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Instrument, SectorSnapshot
from app.services.signal_grade_service import SignalGradeService
from app.utils.numbers import clamp, finite_or_none

_CODE_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")
BOARD_KIND_INDUSTRY = "industry"
BOARD_KIND_CONCEPT = "concept"

DEFAULT_WEIGHTS = {
    "volume": 0.15,
    "ma": 0.20,
    "macd": 0.20,
    "kdj": 0.15,
    "rsi": 0.15,
    "td": 0.05,
    "momentum": 0.10,
}


def component_scores(classified: dict[str, Any]) -> dict[str, float]:
    volume = classified.get("volume") or {}
    ma = classified.get("ma") or {}
    macd = classified.get("macd") or {}
    kdj = classified.get("kdj") or {}
    rsi = classified.get("rsi") or {}
    td = classified.get("td") or {}
    vol_map = {"expand": 78.0, "flat": 52.0, "contract": 32.0, "unknown": 0.0}
    ma_map = {"bull": 82.0, "mixed": 50.0, "bear": 22.0, "unknown": 0.0}
    macd_map = {
        "gold": 88.0,
        "bull_cont": 72.0,
        "approach_gold": 62.0,
        "approach_death": 34.0,
        "death": 18.0,
        "bear_cont": 28.0,
        "unknown": 0.0,
    }
    kdj_map = {"low": 72.0, "healthy": 60.0, "high": 38.0, "overbought": 22.0, "death": 18.0, "unknown": 0.0}
    rsi_value = finite_or_none(rsi.get("value"))
    if rsi_value is None:
        rsi_score = 0.0
    elif rsi_value >= 70:
        rsi_score = 28.0
    elif rsi_value >= 60:
        rsi_score = 68.0
    elif rsi_value <= 40:
        rsi_score = 42.0
    else:
        rsi_score = 55.0
    td_map = {"buy": 70.0, "sell": 30.0, "none": 50.0}
    ret5 = finite_or_none(classified.get("return_5d"))
    if ret5 is None:
        momentum = 0.0
    else:
        momentum = round(clamp(50.0 + ret5 * 400.0, 5.0, 95.0), 1)
    return {
        "volume": vol_map.get(str(volume.get("kind")), 0.0),
        "ma": ma_map.get(str(ma.get("kind")), 0.0),
        "macd": macd_map.get(str(macd.get("kind")), 0.0),
        "kdj": kdj_map.get(str(kdj.get("kind")), 0.0),
        "rsi": rsi_score,
        "td": td_map.get(str(td.get("kind")), 50.0),
        "momentum": momentum,
    }


def weighted_score(parts: dict[str, float], weights: dict[str, float]) -> float | None:
    usable = {key: parts[key] for key in weights if parts.get(key, 0) > 0}
    if len(usable) < 4:
        return None
    total_w = sum(weights[key] for key in usable)
    if total_w <= 0:
        return None
    return round(sum(parts[key] * weights[key] for key in usable) / total_w, 1)


class BoardService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.catalog = self.settings.load_board_catalog()
        self.grade = SignalGradeService(self.settings)
        self.weights = dict(self.grade.config.get("board_score_weights") or DEFAULT_WEIGHTS)

    def build(self, db: Session) -> dict[str, Any]:
        grade_payload = self.grade.build(db)
        by_code = {row["ts_code"]: row for row in grade_payload.get("rows") or []}
        instruments = db.scalars(select(Instrument).where(Instrument.enabled.is_(True))).all()
        by_ts = {item.ts_code.upper(): item for item in instruments}

        industry: list[dict[str, Any]] = []
        concept: list[dict[str, Any]] = []
        for board in self.catalog.get("boards") or []:
            packed = self._pack_board(board, by_code, by_ts)
            if packed["kind"] == BOARD_KIND_CONCEPT:
                concept.append(packed)
            else:
                industry.append(packed)

        def _rank(items: list[dict[str, Any]]) -> None:
            scored = sorted(
                [item for item in items if item.get("score") is not None],
                key=lambda item: item["score"],
                reverse=True,
            )
            for index, item in enumerate(scored, start=1):
                item["rank"] = index
            for item in items:
                item.setdefault("rank", None)

        _rank(industry)
        _rank(concept)
        return {
            "version": self.catalog.get("version", "board-catalog-v0.1.0"),
            "grade_version": grade_payload.get("version"),
            "disclaimer": self.catalog.get("disclaimer"),
            "research_only": True,
            "actionable": False,
            "scrapes_eastmoney": False,
            "weights": self.weights,
            "counts": {
                "industry": len(industry),
                "concept": len(concept),
                "industry_with_etf": sum(1 for item in industry if item["members"]),
                "concept_with_etf": sum(1 for item in concept if item["members"]),
            },
            "industry": industry,
            "concept": concept,
        }

    def add_fund(self, db: Session, board_id: str, ts_code: str, name: str | None = None) -> dict[str, Any]:
        board = self._find_board(board_id)
        if board is None:
            raise KeyError(board_id)
        code = ts_code.strip().upper()
        if not _CODE_RE.fullmatch(code):
            raise ValueError("ts_code must look like 512480.SH")
        symbol = code.split(".", 1)[0]
        exchange = code.split(".", 1)[1]
        row = db.scalar(select(Instrument).where(Instrument.ts_code == code))
        if row is None:
            row = Instrument(
                ts_code=code,
                symbol=symbol,
                name=(name or "").strip() or f"{board['name']}ETF",
                kind="ETF",
                exchange=exchange,
                theme_l1="行业" if board["kind"] == BOARD_KIND_INDUSTRY else "概念",
                theme_l2=board["name"],
                enabled=True,
                metadata_json={"board_ids": [board_id], "user_added": True},
            )
            db.add(row)
        else:
            meta = dict(row.metadata_json or {})
            ids = [str(item) for item in (meta.get("board_ids") or [])]
            if board_id not in ids:
                ids.append(board_id)
            meta["board_ids"] = ids
            meta["user_added"] = True
            row.metadata_json = meta
            row.enabled = True
            if name and name.strip():
                row.name = name.strip()
            if not row.theme_l2:
                row.theme_l2 = board["name"]
        db.flush()
        return {"board_id": board_id, "ts_code": code, "name": row.name, "needs_bars": True}

    def _find_board(self, board_id: str) -> dict[str, Any] | None:
        for board in self.catalog.get("boards") or []:
            if board.get("id") == board_id:
                return board
        return None

    def market_overview(self, db: Session, kind: str | None = None) -> dict[str, Any]:
        """行业/概念板块市场总览（PR-E 一等页数据源）。

        板块行 = catalog 板块 + 最新 SectorSnapshot 广度 + ETF 代理动作/涨跌。
        广度缺失时诚实标注 unavailable，不用成员 ETF 涨跌冒充板块指数。
        """
        base = self.build(db)
        all_boards = list(base.get("industry", [])) + list(base.get("concept", []))

        # 一次性取每个 (board_type, sector_name) 的最新广度行
        breadth: dict[tuple[str, str], SectorSnapshot] = {}
        names_by_kind: dict[str, set[str]] = {}
        for item in all_boards:
            names_by_kind.setdefault(item["kind"], set()).add(item["name"])
        for k, names in names_by_kind.items():
            if not names:
                continue
            latest_dates = (
                select(
                    SectorSnapshot.sector_name.label("name"),
                    func.max(SectorSnapshot.trade_date).label("max_date"),
                )
                .where(SectorSnapshot.board_type == k, SectorSnapshot.sector_name.in_(names))
                .group_by(SectorSnapshot.sector_name)
                .subquery()
            )
            rows = db.scalars(
                select(SectorSnapshot).join(
                    latest_dates,
                    and_(
                        SectorSnapshot.sector_name == latest_dates.c.name,
                        SectorSnapshot.trade_date == latest_dates.c.max_date,
                        SectorSnapshot.board_type == k,
                    ),
                )
            ).all()
            for row in rows:
                breadth[(k, row.sector_name)] = row
        trade_date = max((row.trade_date for row in breadth.values()), default=None)

        for item in all_boards:
            row = breadth.get((item["kind"], item["name"]))
            if row is not None:
                total = int(row.total_count or (row.up_count or 0) + (row.down_count or 0) + (row.flat_count or 0))
                down_ratio = round((row.down_count or 0) / total * 100, 1) if total else None
                item["breadth"] = {
                    "trade_date": row.trade_date.isoformat(),
                    "up": row.up_count,
                    "down": row.down_count,
                    "flat": row.flat_count,
                    "total": total,
                    "down_ratio": down_ratio,
                    "source": row.source,
                }
                item["sector_pct_change"] = row.pct_change
            else:
                item["breadth"] = None
                item["sector_pct_change"] = None

        selected = [item for item in all_boards if kind is None or item["kind"] == kind]
        selected.sort(
            key=lambda item: (
                item["sector_pct_change"] if item["sector_pct_change"] is not None else -999,
                item["pct_change"] if item["pct_change"] is not None else -999,
            ),
            reverse=True,
        )
        return {
            "version": base.get("version"),
            "research_only": True,
            "actionable": False,
            "scrapes_eastmoney": False,
            "coverage_note": "板块行为 ETF 代理与板块涨跌家数快照，非东财板块指数行情",
            "trade_date": trade_date.isoformat() if trade_date else None,
            "kind": kind,
            "counts": {
                "total": len(selected),
                "with_breadth": sum(1 for item in selected if item["breadth"]),
                "with_etf": sum(1 for item in selected if item["members"]),
            },
            "boards": selected,
        }

    def _pack_board(
        self,
        board: dict[str, Any],
        by_code: dict[str, dict[str, Any]],
        by_ts: dict[str, Instrument],
    ) -> dict[str, Any]:
        members: list[dict[str, Any]] = []
        seen: set[str] = set()
        for code in board.get("proxy_codes") or []:
            self._append_member(code, board, by_code, by_ts, members, seen)
        for instrument in by_ts.values():
            if instrument.ts_code.upper() in seen:
                continue
            meta_ids = (instrument.metadata_json or {}).get("board_ids") or []
            if board["id"] in meta_ids or self._keyword_hit(board, instrument):
                self._append_member(instrument.ts_code, board, by_code, by_ts, members, seen)

        primary = members[0] if members else None
        scores = [item["score"] for item in members if item.get("score") is not None]
        return {
            "id": board["id"],
            "kind": board.get("kind", BOARD_KIND_INDUSTRY),
            "name": board["name"],
            "em_code": board.get("em_code") or None,
            "has_proxy": bool(members),
            "coverage": "etf_proxy" if members else "unverified",
            "note": "池内主题ETF代理，非东财板块指数" if members else "无场内ETF代理 · 未验证 / 不可用",
            "members": members,
            "primary_ts_code": primary["ts_code"] if primary else None,
            "pct_change": primary["pct_change"] if primary else None,
            "grade": primary["grade"] if primary else "数据异常",
            "score": round(sum(scores) / len(scores), 1) if scores else None,
            "components": primary["components"] if primary else None,
            "engine_score": primary.get("engine_score") if primary else None,
        }

    def _append_member(
        self,
        ts_code: str,
        board: dict[str, Any],
        by_code: dict[str, dict[str, Any]],
        by_ts: dict[str, Instrument],
        members: list[dict[str, Any]],
        seen: set[str],
    ) -> None:
        code = ts_code.upper()
        if code in seen:
            return
        seen.add(code)
        instrument = by_ts.get(code)
        row = by_code.get(code)
        if row is None:
            members.append(
                {
                    "ts_code": code,
                    "name": instrument.name if instrument else code,
                    "in_universe": instrument is not None,
                    "pct_change": None,
                    "grade": "数据异常",
                    "score": None,
                    "components": None,
                    "engine_score": None,
                    "needs_bars": True,
                }
            )
            return
        parts = component_scores(row)
        members.append(
            {
                "ts_code": code,
                "name": row.get("name") or code,
                "in_universe": True,
                "pct_change": row.get("pct_change"),
                "grade": row.get("grade"),
                "score": weighted_score(parts, self.weights),
                "components": parts,
                "engine_score": None,
                "needs_bars": False,
                "volume": row.get("volume"),
                "ma": row.get("ma"),
                "macd": row.get("macd"),
                "kdj": row.get("kdj"),
                "rsi": row.get("rsi"),
                "td": row.get("td"),
                "forecast": row.get("forecast"),
            }
        )

    @staticmethod
    def _keyword_hit(board: dict[str, Any], instrument: Instrument) -> bool:
        haystack = f"{instrument.name or ''} {instrument.theme_l2 or ''} {instrument.theme_l1 or ''}"
        return any(keyword and keyword in haystack for keyword in (board.get("keywords") or []))
