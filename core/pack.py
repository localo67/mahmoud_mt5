"""Charge un pack de strategie depuis packs/<id>/pack.json."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.session import VALID_KINDS
from core.types import SymbolSpec

ROOT = Path(__file__).resolve().parents[1]
PACKS_ROOT = ROOT / "packs"


def _session_kind(raw: dict[str, Any]) -> str:
    kind = str(raw.get("session_kind") or "clock")
    if kind not in VALID_KINDS:
        raise ValueError(f"session_kind inconnu: {kind!r}")
    return kind


@dataclass(frozen=True)
class PackConfig:
    id: str
    symbol: str
    fast_timeframe: str
    slow_timeframe: str
    session_tz: str
    session_kind: str
    session_start_hour: int
    session_end_hour: int
    max_spread: float
    tp_spread_mult: float
    sl_spread_mult: float
    max_trades_per_day: int
    cooldown_after_sl_seconds: int
    ledger: str
    magic: int
    news_fail_safe: bool
    ema_period: int
    impulse_spread_mult: float
    reward_risk: float
    min_bars_fast: int
    min_bars_slow: int
    allow_overnight: bool
    fallback_spec: SymbolSpec
    raw: dict[str, Any]


def available_packs() -> list[str]:
    if not PACKS_ROOT.is_dir():
        return []
    found = []
    for path in sorted(PACKS_ROOT.iterdir()):
        if path.is_dir() and (path / "pack.json").is_file():
            found.append(path.name)
    return found


def spec_from_mapping(payload: dict[str, Any], name: str) -> SymbolSpec:
    return SymbolSpec(
        name=str(payload.get("name") or name),
        digits=int(payload.get("digits") or 5),
        point=float(payload["point"]),
        trade_tick_size=float(payload["trade_tick_size"]),
        trade_tick_value=float(payload.get("trade_tick_value") or 0.0),
        trade_tick_value_profit=float(payload.get("trade_tick_value_profit") or 0.0),
        trade_tick_value_loss=float(payload.get("trade_tick_value_loss") or 0.0),
        trade_contract_size=float(payload.get("trade_contract_size") or 0.0),
        trade_calc_mode=int(payload.get("trade_calc_mode") or 0),
        currency_profit=str(payload.get("currency_profit") or "USD"),
        currency_margin=str(payload.get("currency_margin") or "USD"),
        volume_min=float(payload["volume_min"]),
        volume_max=float(payload.get("volume_max") or payload["volume_min"]),
        volume_step=float(payload["volume_step"]),
        volume_limit=float(payload.get("volume_limit") or 0.0),
        trade_stops_level=int(payload.get("trade_stops_level") or 0),
        trade_freeze_level=int(payload.get("trade_freeze_level") or 0),
        filling_mode=int(payload.get("filling_mode") or 1),
    )


def load_pack(pack_id: str) -> PackConfig:
    pack_id = (pack_id or "").strip()
    known = available_packs()
    if pack_id not in known:
        raise ValueError(
            f"Pack inconnu: {pack_id!r}. Disponibles: {', '.join(known) or '(aucun)'}"
        )
    raw = json.loads((PACKS_ROOT / pack_id / "pack.json").read_text(encoding="utf-8"))
    symbol = str(raw["symbol"])
    return PackConfig(
        id=str(raw.get("id") or pack_id),
        symbol=symbol,
        fast_timeframe=str(raw.get("fast_timeframe") or "M5"),
        slow_timeframe=str(raw.get("slow_timeframe") or "M15"),
        session_tz=str(raw.get("session_tz") or "America/New_York"),
        session_kind=_session_kind(raw),
        session_start_hour=int(raw.get("session_start_hour") or 9),
        session_end_hour=int(raw.get("session_end_hour") or 17),
        max_spread=float(raw["max_spread"]),
        tp_spread_mult=float(raw.get("tp_spread_mult") or 4.0),
        sl_spread_mult=float(raw.get("sl_spread_mult") or 2.0),
        max_trades_per_day=int(raw.get("max_trades_per_day") or 1),
        cooldown_after_sl_seconds=int(raw.get("cooldown_after_sl_seconds") or 0),
        ledger=str(raw.get("ledger") or f"data/ledger-{pack_id}.sqlite"),
        magic=int(raw.get("magic") or 20240601),
        news_fail_safe=bool(raw.get("news_fail_safe", True)),
        ema_period=int(raw.get("ema_period") or 20),
        impulse_spread_mult=float(raw.get("impulse_spread_mult") or 1.5),
        reward_risk=float(raw.get("reward_risk") or 1.5),
        min_bars_fast=int(raw.get("min_bars_fast") or 50),
        min_bars_slow=int(raw.get("min_bars_slow") or 50),
        allow_overnight=bool(raw.get("allow_overnight", False)),
        fallback_spec=spec_from_mapping(raw.get("fallback_spec") or {}, symbol),
        raw=raw,
    )


def build_strategy(pack: PackConfig):
    module = importlib.import_module(f"packs.{pack.id}.strategy")
    factory = getattr(module, "build", None)
    if factory is not None:
        return factory(pack)
    cls = getattr(module, "Strategy")
    return cls(pack)


def resolve_pack_id(cli_pack: Optional[str] = None, env_pack: Optional[str] = None) -> str:
    chosen = (cli_pack or env_pack or "").strip()
    if chosen:
        return chosen
    return "session_breakout_xauusd"
