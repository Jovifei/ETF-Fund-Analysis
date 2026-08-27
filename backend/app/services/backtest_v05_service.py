from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import json
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models import ReportArtifact
from app.services.backtest_service import RotationBacktestService
from app.services.event_service import emit_event
from app.utils.advanced_indicators import cmf, mfi, rsrs
from app.utils.hashing import stable_hash


class RotationBacktestV05Service(RotationBacktestService):
    """Adds v0.5 factor families while reusing the same event-driven execution engine."""

    @staticmethod
    def _latest_flow_structure(history: pd.DataFrame) -> dict[str, float]:
        close = history["close"].astype(float)
        high = history["high"].astype(float)
        low = history["low"].astype(float)
        volume = history["volume"].astype(float).fillna(0.0)
        amount = history["amount"].astype(float).fillna(0.0)
        cmf20 = float(cmf(high, low, close, volume, 20).iloc[-1])
        mfi14 = float(mfi(high, low, close, volume, 14).iloc[-1])
        volume_ma20 = float(volume.tail(20).mean())
        amount_ma20 = float(amount.tail(20).mean())
        volume_ratio = float(volume.iloc[-1] / volume_ma20) if volume_ma20 > 0 else 0.0
        amount_ratio = float(amount.iloc[-1] / amount_ma20) if amount_ma20 > 0 else volume_ratio
        prior_high20 = float(high.iloc[-21:-1].max()) if len(high) >= 21 else float(high.iloc[:-1].max())
        prior_low20 = float(low.iloc[-21:-1].min()) if len(low) >= 21 else float(low.iloc[:-1].min())
        prior_high55 = float(high.iloc[-56:-1].max()) if len(high) >= 56 else prior_high20
        spread20 = max(1e-12, prior_high20 - prior_low20)
        box_position = float((close.iloc[-1] - prior_low20) / spread20)
        box_range = float(spread20 / prior_low20) if prior_low20 > 0 else 0.0
        breakout20 = float(close.iloc[-1] / prior_high20 - 1) if prior_high20 > 0 else -1.0
        breakout55 = float(close.iloc[-1] / prior_high55 - 1) if prior_high55 > 0 else -1.0
        vwap_den = float(volume.tail(20).sum())
        typical = (high + low + close) / 3
        vwap20 = float((typical * volume).tail(20).sum() / vwap_den) if vwap_den > 0 else float(close.iloc[-1])
        vwap_distance = float(close.iloc[-1] / vwap20 - 1) if vwap20 > 0 else 0.0
        pullback = 0.0
        if len(history) >= 45:
            rolling_high = high.shift(1).rolling(20).max()
            rolling_volume = volume.rolling(20).mean()
            ignition = close.pct_change().ge(0.02) & close.ge(rolling_high * 0.98) & volume.ge(rolling_volume * 1.35)
            recent = ignition.tail(13)
            if bool(recent.any()):
                ignition_date = recent[recent].index[-1]
                pos = history.index.get_loc(ignition_date)
                ignition_volume = float(volume.iloc[pos])
                post = volume.iloc[pos+1:pos+6]
                contraction = float(post.mean() / ignition_volume) if len(post) and ignition_volume > 0 else 1.0
                support = max(float(low.iloc[pos]) * 0.97, float(rolling_high.iloc[pos]) * 0.96)
                if float(close.iloc[-1]) >= support and contraction <= 0.90:
                    pullback = min(1.0, max(0.0, (0.90-contraction)/0.50 + 0.4))
        _, _, _, z = rsrs(high.tail(90), low.tail(90), 18, 60)
        return {
            "cmf20": cmf20, "mfi14": mfi14, "volume_ratio": volume_ratio, "amount_ratio": amount_ratio,
            "breakout20": breakout20, "breakout55": breakout55, "box_position": box_position,
            "box_range": box_range, "vwap_distance": vwap_distance, "pullback": pullback,
            "rsrs_z": float(z.iloc[-1]),
        }

    def _feature_table(self, frames: dict[str, pd.DataFrame], as_of: date) -> pd.DataFrame:
        table = super()._feature_table(frames, as_of)
        if table.empty:
            return table
        extras: list[dict] = []
        for code in table.index.tolist():
            history = frames[code].loc[frames[code].index <= as_of]
            extras.append({"ts_code": code, **self._latest_flow_structure(history)})
        extra = pd.DataFrame(extras).set_index("ts_code")
        table = table.drop(columns=[c for c in extra.columns if c in table.columns], errors="ignore").join(extra, how="left")
        table["rank_return_5"] = self._percentile_rank(table["return_5"])
        table["rank_return_20"] = self._percentile_rank(table["return_20"])
        table["rank_return_60"] = self._percentile_rank(table["return_60"])
        table["rank_trend_20"] = self._percentile_rank(table["trend_20"])
        table["rank_low_volatility"] = 1.0 - self._percentile_rank(table["volatility_20"])
        flow_raw = table["cmf20"].clip(-0.5, 0.5) + (table["mfi14"]-50)/100 + np.log1p(table["volume_ratio"].clip(lower=0))*0.20
        breakout_raw = table["breakout20"].clip(-0.2,0.2)*2 + table["breakout55"].clip(-0.2,0.2) + (table["box_position"].clip(-0.5,1.5)-0.5)*0.15
        structure_raw = -table["vwap_distance"].abs() + table["pullback"]*0.10 - (table["box_range"]-0.15).abs()*0.10
        table["rank_volume_flow"] = self._percentile_rank(flow_raw)
        table["rank_breakout"] = self._percentile_rank(breakout_raw)
        table["rank_structure"] = self._percentile_rank(structure_raw)
        table["rank_rsrs"] = self._percentile_rank(table["rsrs_z"])
        table["rank_pullback"] = self._percentile_rank(table["pullback"])
        defaults = {"return_5":.10,"return_20":.20,"return_60":.15,"trend_20":.10,"low_volatility":.10,"volume_flow":.12,"breakout":.10,"rsrs":.06,"structure":.04,"pullback":.03}
        defaults.update({k: float(v) for k,v in (self.config.get("factor_weights") or {}).items() if k in defaults})
        cols = {"return_5":"rank_return_5","return_20":"rank_return_20","return_60":"rank_return_60","trend_20":"rank_trend_20","low_volatility":"rank_low_volatility","volume_flow":"rank_volume_flow","breakout":"rank_breakout","rsrs":"rank_rsrs","structure":"rank_structure","pullback":"rank_pullback"}
        total = sum(max(0.0, defaults[k]) for k in cols) or 1.0
        table["score"] = sum(table[c]*max(0.0, defaults[k]) for k,c in cols.items())/total
        table["absolute_momentum"] = table["return_20"]*.50 + table["return_60"]*.30 + table["trend_20"]*.15 + table["cmf20"]*.05
        return table.sort_values("score", ascending=False)

    def _regime(self, benchmark: pd.DataFrame, as_of: date) -> tuple[str, float, dict]:
        label, cap, evidence = super()._regime(benchmark, as_of)
        history = benchmark.loc[benchmark.index <= as_of]
        rsrs_z = float(self._latest_flow_structure(history)["rsrs_z"])
        caps = self.config.get("portfolio_exposure_caps", {})
        if rsrs_z <= -1.2: label = "extreme_risk"
        elif rsrs_z <= -0.7: label = "high_risk"
        elif label == "low_risk" and rsrs_z < 0: label = "normal"
        cap = float(caps.get(label, cap))
        evidence["rsrs_zscore"] = round(rsrs_z, 4)
        return label, cap, evidence

    def run_ablation(self, db: Session, run_id: str | None = None) -> dict:
        run_id = run_id or uuid4().hex
        original = deepcopy(self.config)
        full = deepcopy(original.get("factor_weights") or {})
        variants = {
            "momentum_baseline":{"return_5":.15,"return_20":.35,"return_60":.25,"trend_20":.15,"low_volatility":.10,"volume_flow":0,"breakout":0,"rsrs":0,"structure":0,"pullback":0},
            "plus_volume_flow":{"return_5":.12,"return_20":.28,"return_60":.20,"trend_20":.12,"low_volatility":.10,"volume_flow":.18,"breakout":0,"rsrs":0,"structure":0,"pullback":0},
            "plus_breakout_structure":{"return_5":.10,"return_20":.23,"return_60":.17,"trend_20":.10,"low_volatility":.10,"volume_flow":.13,"breakout":.10,"rsrs":0,"structure":.04,"pullback":.03},
            "full_v050": full or {"return_5":.10,"return_20":.20,"return_60":.15,"trend_20":.10,"low_volatility":.10,"volume_flow":.12,"breakout":.10,"rsrs":.06,"structure":.04,"pullback":.03},
        }
        results, files = {}, []
        try:
            for name, weights in variants.items():
                self.config = deepcopy(original); self.config["factor_weights"] = weights
                result = self.run(db, run_id=f"{run_id}-{name}")
                results[name] = result["metrics"]; files.append(result["filename"])
        finally:
            self.config = original
        baseline = results["momentum_baseline"]
        comparison = {name:{"metrics":metrics,"delta_total_return":round(float(metrics.get("total_return") or 0)-float(baseline.get("total_return") or 0),6),"delta_sharpe":round(float(metrics.get("sharpe_ratio") or 0)-float(baseline.get("sharpe_ratio") or 0),4),"delta_max_drawdown":round(float(metrics.get("max_drawdown") or 0)-float(baseline.get("max_drawdown") or 0),6)} for name,metrics in results.items()}
        now = datetime.now(self.settings.timezone)
        payload = {"run_id":run_id,"generated_at":now.isoformat(),"report_type":"strategy_ablation","strategy_version":self.strategy["version"],"research_status":"ablation_only_not_strategy_promotion","baseline":"momentum_baseline","variants":variants,"comparison":comparison,"component_reports":files,"audit":{"same_execution_engine":True,"decision_at":"close_t","execution_at":"open_t_plus_1","costs_included":True,"only_factor_weights_changed":True}}
        content_hash = stable_hash(payload); self.settings.reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"strategy_ablation_{now:%Y%m%d_%H%M%S}_{content_hash[:10]}.json"; path = self.settings.reports_dir/filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        db.add(ReportArtifact(report_type="strategy_ablation", as_of_time=now, file_path=str(path), content_hash=content_hash, metadata_json={"run_id":run_id,"filename":filename,"strategy_version":self.strategy["version"],"comparison":comparison}))
        db.flush(); emit_event(db, "backtest.ablation.completed", {"run_id":run_id,"filename":filename})
        return {"run_id":run_id,"filename":filename,"path":str(path),"url":f"/api/reports/{filename}","content_hash":content_hash,"comparison":comparison,"component_reports":files}
