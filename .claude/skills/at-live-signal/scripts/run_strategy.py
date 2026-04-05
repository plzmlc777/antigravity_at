#!/usr/bin/env python3
"""
Strategy Skill Runner — Python 전략 모듈을 스킬로 실행.

기존 Python 전략 클래스를 그대로 임포트하여, SkillContext + WebSocket 틱 수신으로
엔진 내부 실행과 100% 동일한 동작을 재현합니다.

데이터 흐름 (Python 엔진과 동일):
    Backend WS /ws/watch/{symbol}
        ↓ tick (price, volume, time)
    CandleRealAggregator.add_tick()
        ↓ closed_candle
    strategy.on_data(candle)   ← 캔들 기반 진입/지표
    strategy.on_tick(price)    ← 틱 기반 청산 (trailing stop 등)

Usage:
    python run_strategy.py --session-id <ID> --api-url http://localhost:8001
    python run_strategy.py --session-id <ID> --strategy rsi_martingale --dry-run
"""

import argparse
import asyncio
import importlib
import json
import logging
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Local imports (skill_context, local strategies)
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from skill_context import SkillContext

# Backend path for CandleRealAggregator (data pipeline only, not strategies)
BACKEND_DIR = Path(__file__).resolve().parents[4] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("skill_runner")


# =========================================================================
# API Helpers
# =========================================================================

def fetch_candles(api_url: str, session_id: str, limit: int = 200) -> dict:
    """GET /candles — 세션 정보 + 캔들 데이터."""
    url = f"{api_url}/api/v1/live/session/{session_id}/candles?limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


# =========================================================================
# Strategy Loader
# =========================================================================

def load_strategy_class(strategy_name: str):
    """로컬 strategies/ 패키지에서 전략 클래스를 동적 임포트."""
    try:
        module = importlib.import_module(f"strategies.{strategy_name}")
    except ImportError as e:
        raise ImportError(
            f"Strategy '{strategy_name}' not found in strategies/ folder. "
            f"Add strategies/{strategy_name}.py to use it. Error: {e}"
        )

    from strategies.base import BaseStrategy as LocalBase
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (isinstance(attr, type)
                and issubclass(attr, LocalBase)
                and attr is not LocalBase
                and attr.__module__ == module.__name__):
            logger.info(f"Loaded strategy '{strategy_name}' from strategies/")
            return attr

    raise ValueError(f"No BaseStrategy subclass found in strategies/{strategy_name}.py")


# =========================================================================
# WebSocket Tick Runner (mirrors LiveTradingEngine)
# =========================================================================

async def run_websocket(args):
    """WebSocket 틱 수신 → CandleRealAggregator → on_data/on_tick."""
    import websockets
    from app.core.live_aggregator import CandleRealAggregator

    logger.info("=== Skill Strategy Runner (WebSocket Mode) ===")
    logger.info(f"Session: {args.session_id}")
    logger.info(f"API: {args.api_url}")
    logger.info(f"Dry-run: {args.dry_run}")

    # 1. Fetch session info + initial candles
    logger.info("Fetching session data...")
    data = fetch_candles(args.api_url, args.session_id, limit=300)

    symbol = data["symbol"]
    candles = data["candles"]
    current_price = data.get("current_price", 0)
    session_config = data.get("strategy_config", {})
    session_strategy = data.get("strategy_name", "rsi_martingale")
    initial_capital = data.get("initial_capital", 500)

    # Override strategy/config from CLI if provided
    strategy_name = args.strategy or session_strategy
    if args.config:
        config = json.loads(args.config)
        merged = {**session_config, **config}
    else:
        merged = session_config

    # Inject symbol into config (martingale_base reads config["symbol"])
    merged["symbol"] = symbol

    logger.info(f"Symbol: {symbol}")
    logger.info(f"Strategy: {strategy_name}")
    logger.info(f"Candles loaded: {len(candles)}")
    logger.info(f"Current price: {current_price}")
    logger.info(f"Capital: {initial_capital}")

    # 2. Load strategy class
    strategy_class = load_strategy_class(strategy_name)
    logger.info(f"Strategy class: {strategy_class.__name__}")

    # 3. Create SkillContext
    context = SkillContext(
        session_id=args.session_id,
        api_url=args.api_url,
        initial_capital=initial_capital,
        config=merged,
        submit_to_engine=not args.dry_run,
    )
    context.price_map[symbol] = current_price

    # 4. Initialize strategy
    strategy = strategy_class(context, merged)
    strategy.initialize()
    logger.info("Strategy initialized.")

    # 5. Preload history
    if hasattr(strategy, 'preload_history') and candles:
        history = candles[:-1] if len(candles) > 1 else candles
        strategy.preload_history(history)
        logger.info(f"History preloaded: {len(history)} candles")

    # 6. Create CandleRealAggregator (same as LiveTradingEngine)
    interval_str = merged.get("interval", "1m")
    interval_minutes = int(interval_str.replace("m", "").replace("h", "")) if "h" not in interval_str else int(interval_str.replace("h", "")) * 60
    aggregator = CandleRealAggregator(symbol, interval_minutes=interval_minutes)
    logger.info(f"Aggregator interval: {interval_str} ({interval_minutes}min)")

    has_on_tick = hasattr(strategy, 'on_tick') and getattr(strategy, 'tick_execution', 'candle') == 'tick'
    logger.info(f"Tick execution: {has_on_tick}")
    logger.info("=" * 60)

    # 7. Connect to backend WebSocket for real-time ticks
    # Use session WS (/ws/{session_id}) for ticks from the engine (same data as Python strategy)
    # Falls back to symbol WS (/ws/watch/{symbol}) if --ws-source is "symbol"
    ws_scheme = "ws" if args.api_url.startswith("http://") else "wss"
    ws_host = args.api_url.replace("http://", "").replace("https://", "")
    if args.ws_source and args.ws_source != "session":
        ws_url = f"{ws_scheme}://{ws_host}/api/v1/live/ws/watch/{symbol}"
    else:
        # Connect to noop session WS — receives same ticks as Python engine
        ws_url = f"{ws_scheme}://{ws_host}/api/v1/live/ws/{args.session_id}"
    logger.info(f"Connecting to WebSocket: {ws_url}")

    tick_count = 0
    candle_count = 0
    consecutive_errors = 0
    max_errors = 10

    while consecutive_errors < max_errors:
        try:
            async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
                logger.info("WebSocket connected!")
                consecutive_errors = 0

                async for message in ws:
                    try:
                        tick = json.loads(message)
                        if tick.get("type") != "tick":
                            continue

                        price = tick.get("price", 0)
                        volume = tick.get("volume", 0)
                        ts_str = tick.get("time", "")

                        if price <= 0:
                            continue

                        # Parse timestamp
                        try:
                            ts = datetime.fromisoformat(ts_str)
                        except (ValueError, TypeError):
                            ts = datetime.now()

                        tick_count += 1
                        context.price_map[symbol] = price
                        context.current_timestamp = ts

                        # Feed tick to aggregator (same as LiveTradingEngine)
                        closed_candle, _snapshot = aggregator.add_tick(price, volume, ts)

                        # Tick-level exit check (same as engine.process_realtime_tick)
                        if has_on_tick:
                            exited = strategy.on_tick(price)
                            if exited:
                                equity = context.get_total_equity()
                                pnl = context.calculate_pnl()
                                logger.info(
                                    f"  TICK EXIT @ {price:.4f} | "
                                    f"equity={equity:,.2f} cash={context.cash:,.2f} "
                                    f"holdings={context.holdings} pnl={pnl:+,.4f}"
                                )

                        # Candle closed → on_data
                        if closed_candle:
                            candle_count += 1
                            logger.info(
                                f"Candle #{candle_count}: {closed_candle['timestamp']} "
                                f"O={closed_candle['open']:.4f} H={closed_candle['high']:.4f} "
                                f"L={closed_candle['low']:.4f} C={closed_candle['close']:.4f} "
                                f"V={closed_candle['volume']}"
                            )

                            strategy.on_data(closed_candle)

                            # RSI state logging
                            rsi_val = getattr(strategy, '_current_rsi', None)
                            prev_rsi = getattr(strategy, '_prev_rsi', None)
                            armed = getattr(strategy, '_long_trigger_armed', None)
                            if rsi_val is not None:
                                logger.info(
                                    f"  RSI: {rsi_val:.2f} (prev={prev_rsi:.2f}) "
                                    f"armed={armed} trigger={strategy.config.get('trigger_level', '?')}"
                                )

                            # Status
                            equity = context.get_total_equity()
                            pnl = context.calculate_pnl()
                            logger.info(
                                f"  Status: equity={equity:,.2f} cash={context.cash:,.2f} "
                                f"holdings={context.holdings} pnl={pnl:+,.4f} "
                                f"trades={len(context.trades)} ticks={tick_count}"
                            )

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.error(f"Tick processing error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("Cancelled.")
            break
        except KeyboardInterrupt:
            logger.info("\nStopped by user.")
            break
        except Exception as e:
            consecutive_errors += 1
            logger.warning(f"WebSocket error ({consecutive_errors}/{max_errors}): {e}")
            await asyncio.sleep(5)

    # Print summary
    logger.info("=" * 60)
    logger.info("=== Session Summary ===")
    logger.info(f"Total candles: {candle_count}")
    logger.info(f"Total ticks: {tick_count}")
    logger.info(f"Total trades: {len(context.trades)}")
    logger.info(f"Final equity: {context.get_total_equity():,.2f}")
    logger.info(f"Total PnL: {context.calculate_pnl():+,.4f}")
    logger.info(f"Holdings: {context.holdings}")

    if context.trades:
        logger.info("\n--- Trade Log ---")
        for t in context.trades[-20:]:
            logger.info(
                f"  {t.get('type', '?'):6s} | {t.get('symbol', '?'):12s} | "
                f"qty={t.get('quantity', 0):>10} | price={t.get('price', 0):>10.4f} | "
                f"pnl={t.get('realized_pnl', 0):>+8.4f}"
            )


# =========================================================================
# Fallback: REST Polling (if WebSocket unavailable)
# =========================================================================

def run_polling(args):
    """REST 폴링 방식 (WebSocket 불가 시 fallback)."""
    logger.info("=== Skill Strategy Runner (Polling Mode) ===")
    logger.info(f"Session: {args.session_id}")
    logger.info(f"API: {args.api_url}")

    data = fetch_candles(args.api_url, args.session_id, limit=300)
    symbol = data["symbol"]
    candles = data["candles"]
    current_price = data.get("current_price", 0)
    session_config = data.get("strategy_config", {})
    session_strategy = data.get("strategy_name", "rsi_martingale")
    initial_capital = data.get("initial_capital", 500)

    strategy_name = args.strategy or session_strategy
    merged = {**session_config, **(json.loads(args.config) if args.config else {})}
    merged["symbol"] = symbol

    logger.info(f"Symbol: {symbol}, Strategy: {strategy_name}, Candles: {len(candles)}")

    strategy_class = load_strategy_class(strategy_name)
    context = SkillContext(
        session_id=args.session_id, api_url=args.api_url,
        initial_capital=initial_capital, config=merged,
        submit_to_engine=not args.dry_run,
    )
    context.price_map[symbol] = current_price

    strategy = strategy_class(context, merged)
    strategy.initialize()

    if hasattr(strategy, 'preload_history') and candles:
        history = candles[:-1] if len(candles) > 1 else candles
        strategy.preload_history(history)
        logger.info(f"History preloaded: {len(history)} candles")

    last_candle_ts = candles[-1]["timestamp"] if candles else None
    has_on_tick = hasattr(strategy, 'on_tick') and getattr(strategy, 'tick_execution', 'candle') == 'tick'
    logger.info(f"Polling interval: {args.poll_interval}s, Tick execution: {has_on_tick}")
    logger.info("=" * 60)

    consecutive_errors = 0
    import time
    try:
        while True:
            try:
                recent = fetch_candles(args.api_url, args.session_id, limit=5)
                recent_candles = recent.get("candles", [])
                new_price = recent.get("current_price", 0)

                if new_price > 0:
                    context.price_map[symbol] = new_price
                    if has_on_tick:
                        exited = strategy.on_tick(new_price)
                        if exited:
                            equity = context.get_total_equity()
                            pnl = context.calculate_pnl()
                            logger.info(
                                f"  TICK EXIT @ {new_price:.4f} | "
                                f"equity={equity:,.2f} cash={context.cash:,.2f} "
                                f"holdings={context.holdings} pnl={pnl:+,.4f}"
                            )

                new_candles = [c for c in recent_candles if last_candle_ts and c["timestamp"] > last_candle_ts]
                if new_candles:
                    for candle in new_candles:
                        ts = candle["timestamp"]
                        context.current_timestamp = datetime.fromisoformat(ts)
                        context.price_map[symbol] = candle["close"]
                        logger.info(
                            f"Candle: {ts} O={candle['open']:.4f} H={candle['high']:.4f} "
                            f"L={candle['low']:.4f} C={candle['close']:.4f} V={candle.get('volume', 0):.1f}"
                        )
                        strategy.on_data(candle)

                        rsi_val = getattr(strategy, '_current_rsi', None)
                        if rsi_val is not None:
                            logger.info(
                                f"  RSI: {rsi_val:.2f} (prev={getattr(strategy, '_prev_rsi', 0):.2f}) "
                                f"armed={getattr(strategy, '_long_trigger_armed', None)}"
                            )
                        last_candle_ts = ts

                    equity = context.get_total_equity()
                    pnl = context.calculate_pnl()
                    logger.info(
                        f"Status: equity={equity:,.2f} cash={context.cash:,.2f} "
                        f"holdings={context.holdings} pnl={pnl:+,.4f} trades={len(context.trades)}"
                    )
                consecutive_errors = 0
            except urllib.error.URLError as e:
                consecutive_errors += 1
                logger.warning(f"API error ({consecutive_errors}/10): {e}")
                if consecutive_errors >= 10:
                    break
                time.sleep(5)
                continue
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error ({consecutive_errors}/10): {e}", exc_info=True)
                if consecutive_errors >= 10:
                    break
                time.sleep(5)
                continue
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        logger.info("\nStopped by user.")

    logger.info("=" * 60)
    logger.info(f"Total trades: {len(context.trades)}, PnL: {context.calculate_pnl():+,.4f}")


def main():
    parser = argparse.ArgumentParser(
        description="Run a Python trading strategy as a skill (WebSocket tick + candle aggregation)"
    )
    parser.add_argument("--session-id", required=True, help="Live session ID")
    parser.add_argument("--strategy", default=None, help="Strategy name (default: from session)")
    parser.add_argument("--config", default=None, help="Strategy config JSON override")
    parser.add_argument("--api-url", default="http://localhost:8001", help="Backend API URL")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="Polling interval (fallback mode)")
    parser.add_argument("--dry-run", action="store_true", help="Local simulation only")
    parser.add_argument("--mode", choices=["ws", "poll"], default="ws",
                        help="Data mode: 'ws' for WebSocket ticks (default), 'poll' for REST polling")
    parser.add_argument("--ws-source", choices=["session", "symbol"], default="session",
                        help="WS source: 'session' (engine ticks, default), 'symbol' (market data router)")
    args = parser.parse_args()

    if args.mode == "ws":
        try:
            import websockets  # noqa: F401
            asyncio.run(run_websocket(args))
        except ImportError:
            logger.warning("websockets not installed. Falling back to polling mode.")
            logger.warning("Install with: pip install websockets")
            run_polling(args)
    else:
        run_polling(args)


if __name__ == "__main__":
    main()
