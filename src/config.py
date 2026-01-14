import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class RiskConfig:
    max_position_per_market: float
    max_global_exposure: float
    max_daily_loss: float
    max_orders_per_minute: int


@dataclass
class StrategyConfig:
    anomaly_threshold: float
    min_impact_per_volume: float
    take_profit_bps: int
    stop_loss_bps: int
    time_stop_min: int
    atr_window: int


@dataclass
class DetectorConfig:
    volume_windows_sec: List[int]
    baseline_window_sec: int
    churn_window_sec: int
    repeat_print_window_sec: int
    spread_window_sec: int
    imbalance_depth_levels: int


@dataclass
class ExecutionConfig:
    order_size_default: float
    order_size_percent_wallet: Optional[float]
    wallet_balance_override: Optional[float]
    rate_limit_per_minute: int
    retry_attempts: int
    retry_backoff_sec: float


@dataclass
class PolymarketConfig:
    rest_base_url: str
    ws_url: Optional[str]
    api_key: Optional[str]
    api_secret: Optional[str]
    api_passphrase: Optional[str]
    wallet_signer_mode: str
    private_key: Optional[str]
    wallet_signer_url: Optional[str]
    wallet_public_key: Optional[str]


@dataclass
class AlertsConfig:
    discord_webhook_url: str
    throttle_sec: int
    batch_size: int


@dataclass
class AppConfig:
    trading_mode: str
    allowlist_markets: List[str]
    top_n_by_volume: Optional[int]
    data_poll_sec: int
    health_check_sec: int
    polymarket: PolymarketConfig
    detector: DetectorConfig
    strategy: StrategyConfig
    execution: ExecutionConfig
    risk: RiskConfig
    alerts: AlertsConfig
    raw: Dict[str, Any] = field(default_factory=dict)


def _env_override(key: str, default: Optional[str]) -> Optional[str]:
    value = os.environ.get(key)
    if value is None:
        return default
    return value


def _env_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    return int(value)


def _env_float(key: str, default: float) -> float:
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    return float(value)


def _env_list(key: str) -> List[str]:
    value = os.environ.get(key)
    if value is None or value.strip() == "":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    trading_mode = _env_override("TRADING_MODE", raw.get("trading_mode", "simulation"))

    polymarket = raw.get("polymarket", {})
    polymarket_cfg = PolymarketConfig(
        rest_base_url=_env_override("POLYMARKET_REST_BASE_URL", polymarket.get("rest_base_url", "")),
        ws_url=_env_override("POLYMARKET_WS_URL", polymarket.get("ws_url")),
        api_key=_env_override("POLYMARKET_API_KEY", polymarket.get("api_key")),
        api_secret=_env_override("POLYMARKET_API_SECRET", polymarket.get("api_secret")),
        api_passphrase=_env_override("POLYMARKET_API_PASSPHRASE", polymarket.get("api_passphrase")),
        wallet_signer_mode=_env_override("WALLET_SIGNER_MODE", polymarket.get("wallet_signer_mode", "external")),
        private_key=_env_override("PRIVATE_KEY", polymarket.get("private_key")),
        wallet_signer_url=_env_override("WALLET_SIGNER_URL", polymarket.get("wallet_signer_url")),
        wallet_public_key=_env_override("WALLET_PUBLIC_KEY", polymarket.get("wallet_public_key")),
    )

    detector = raw.get("detector", {})
    detector_cfg = DetectorConfig(
        volume_windows_sec=detector.get("volume_windows_sec", [60, 300]),
        baseline_window_sec=_env_int("BASELINE_WINDOW_SEC", detector.get("baseline_window_sec", 1800)),
        churn_window_sec=_env_int("CHURN_WINDOW_SEC", detector.get("churn_window_sec", 300)),
        repeat_print_window_sec=_env_int("REPEAT_PRINT_WINDOW_SEC", detector.get("repeat_print_window_sec", 120)),
        spread_window_sec=_env_int("SPREAD_WINDOW_SEC", detector.get("spread_window_sec", 300)),
        imbalance_depth_levels=_env_int("IMBALANCE_DEPTH_LEVELS", detector.get("imbalance_depth_levels", 5)),
    )

    strategy = raw.get("strategy", {})
    strategy_cfg = StrategyConfig(
        anomaly_threshold=_env_float("ANOMALY_THRESHOLD", strategy.get("anomaly_threshold", 0.75)),
        min_impact_per_volume=_env_float("MIN_IMPACT_PER_VOLUME", strategy.get("min_impact_per_volume", 0.002)),
        take_profit_bps=_env_int("TAKE_PROFIT_BPS", strategy.get("take_profit_bps", 40)),
        stop_loss_bps=_env_int("STOP_LOSS_BPS", strategy.get("stop_loss_bps", 25)),
        time_stop_min=_env_int("TIME_STOP_MIN", strategy.get("time_stop_min", 10)),
        atr_window=_env_int("ATR_WINDOW", strategy.get("atr_window", 14)),
    )

    execution = raw.get("execution", {})
    execution_cfg = ExecutionConfig(
        order_size_default=_env_float("ORDER_SIZE_DEFAULT", execution.get("order_size_default", 10.0)),
        order_size_percent_wallet=_env_float(
            "ORDER_SIZE_PERCENT_WALLET",
            execution.get("order_size_percent_wallet", 0.0),
        )
        or None,
        wallet_balance_override=_env_float(
            "WALLET_BALANCE_OVERRIDE",
            execution.get("wallet_balance_override", 0.0),
        )
        or None,
        rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", execution.get("rate_limit_per_minute", 30)),
        retry_attempts=_env_int("RETRY_ATTEMPTS", execution.get("retry_attempts", 3)),
        retry_backoff_sec=_env_float("RETRY_BACKOFF_SEC", execution.get("retry_backoff_sec", 0.5)),
    )

    risk = raw.get("risk", {})
    risk_cfg = RiskConfig(
        max_position_per_market=_env_float("MAX_POSITION_PER_MARKET", risk.get("max_position_per_market", 100.0)),
        max_global_exposure=_env_float("MAX_GLOBAL_EXPOSURE", risk.get("max_global_exposure", 500.0)),
        max_daily_loss=_env_float("MAX_DAILY_LOSS", risk.get("max_daily_loss", 50.0)),
        max_orders_per_minute=_env_int("MAX_ORDERS_PER_MINUTE", risk.get("max_orders_per_minute", 20)),
    )

    alerts = raw.get("alerts", {})
    alerts_cfg = AlertsConfig(
        discord_webhook_url=_env_override("DISCORD_WEBHOOK_URL", alerts.get("discord_webhook_url", "")),
        throttle_sec=_env_int("ALERT_THROTTLE_SEC", alerts.get("throttle_sec", 15)),
        batch_size=_env_int("ALERT_BATCH_SIZE", alerts.get("batch_size", 5)),
    )

    return AppConfig(
        trading_mode=trading_mode,
        allowlist_markets=_env_list("ALLOWLIST_MARKETS") or raw.get("allowlist_markets", []),
        top_n_by_volume=_env_int("TOP_N_BY_VOLUME", raw.get("top_n_by_volume") or 0) or None,
        data_poll_sec=_env_int("DATA_POLL_SEC", raw.get("data_poll_sec", 5)),
        health_check_sec=_env_int("HEALTH_CHECK_SEC", raw.get("health_check_sec", 30)),
        polymarket=polymarket_cfg,
        detector=detector_cfg,
        strategy=strategy_cfg,
        execution=execution_cfg,
        risk=risk_cfg,
        alerts=alerts_cfg,
        raw=raw,
    )
