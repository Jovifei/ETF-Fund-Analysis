from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class IndustryBoardCoverage:
    direct: int
    proxy: int
    unmapped: int


class IndustryBoardService:
    """Load and validate the screenshot-parity industry/anchor registry.

    A repository seed mapping is not the same as a provider-qualified product.
    The registry therefore preserves the distinction between direct ETF,
    partial theme proxy, and an intentionally unmapped industry.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        config_dir = Path(getattr(self.settings, "config_dir", "config"))
        self.path = config_dir / "industry_board.json"

    def load(self) -> dict[str, Any]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self._validate(payload)
        return payload

    def snapshot(self, available_codes: set[str] | None = None) -> dict[str, Any]:
        payload = self.load()
        available_codes = {code.upper() for code in (available_codes or set())}
        industries: list[dict[str, Any]] = []
        for item in payload["industries"]:
            row = dict(item)
            code = str(row.get("proxy_ts_code") or "").upper()
            row["available_in_universe"] = bool(code and code in available_codes) if available_codes else None
            industries.append(row)
        anchors: list[dict[str, Any]] = []
        for item in payload["market_anchors"]:
            row = dict(item)
            code = str(row.get("proxy_ts_code") or "").upper()
            row["available_in_universe"] = bool(code and code in available_codes) if available_codes else None
            anchors.append(row)
        coverage = self.coverage(payload)
        return {
            "version": payload["version"],
            "classification": payload["classification"],
            "display": payload["display"],
            "coverage": {
                "direct": coverage.direct,
                "proxy": coverage.proxy,
                "unmapped": coverage.unmapped,
                "total": coverage.direct + coverage.proxy + coverage.unmapped,
            },
            "industries": industries,
            "market_anchors": anchors,
            "extended_themes": payload.get("extended_themes", []),
            "generated_at": datetime.now().astimezone().isoformat(),
        }

    @staticmethod
    def coverage(payload: dict[str, Any]) -> IndustryBoardCoverage:
        statuses = [str(item.get("coverage_status")) for item in payload["industries"]]
        return IndustryBoardCoverage(
            direct=statuses.count("direct_etf"),
            proxy=statuses.count("proxy"),
            unmapped=statuses.count("unmapped_pending_qualification"),
        )

    @staticmethod
    def _validate(payload: dict[str, Any]) -> None:
        industries = payload.get("industries")
        if not isinstance(industries, list) or len(industries) != 31:
            raise ValueError("industry_board.json 必须包含31个申万一级行业")
        expected = int(payload.get("classification", {}).get("expected_count", 31))
        if expected != 31:
            raise ValueError("行业分类 expected_count 必须为31")
        ids = [str(item.get("industry_id") or "") for item in industries]
        names = [str(item.get("name") or "") for item in industries]
        orders = [int(item.get("display_order") or 0) for item in industries]
        if len(set(ids)) != 31 or len(set(names)) != 31 or len(set(orders)) != 31:
            raise ValueError("行业ID、名称和展示顺序必须唯一")
        allowed = {"direct_etf", "proxy", "unmapped_pending_qualification"}
        proxy_codes: list[str] = []
        for item in industries:
            status = item.get("coverage_status")
            if status not in allowed:
                raise ValueError(f"不支持的行业覆盖状态: {status}")
            code = item.get("proxy_ts_code")
            if status == "unmapped_pending_qualification" and code:
                raise ValueError(f"未映射行业不能配置ETF代码: {item.get('name')}")
            if code:
                proxy_codes.append(str(code).upper())
        if len(set(proxy_codes)) != len(proxy_codes):
            raise ValueError("行业ETF代理代码不能重复")
        anchors = payload.get("market_anchors")
        anchor_ids = {item.get("id") for item in anchors or []}
        if anchor_ids != {"china_core", "sp500", "nasdaq", "gold"}:
            raise ValueError("市场锚必须包含china_core、sp500、nasdaq、gold")
