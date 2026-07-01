"""
partner_engine.py

Minimal orchestrator for PartnerOS setup verification. Wires together
existing pieces in the order they already expect to be called:
MarketService (candles) -> Candle-to-Bar conversion -> validate_setup().
Prints PASS or FAIL: <FailureStep> and nothing else.

Explicitly out of scope, on purpose: trade execution, order placement,
account/risk management, SL/TP, position sizing, journaling,
analytics, GUI, database, caching, background workers, or any API
layer. If one of those is ever needed, it belongs in its own module.
"""

import os
from typing import List, Optional, Tuple

from twisted.internet import defer, reactor, task

from .ctrader.connector import CTraderConnector, Candle
from .ctrader.market import MarketService
from .ctrader.liquidity import Bar
from .ctrader.direction import Direction
from .ctrader.setup_validator import validate_setup


def _candles_to_bars(candles: List[Candle], digits: int) -> List[Bar]:
    # Reuses CTraderConnector._relative_price_to_real() -- the existing
    # single source of truth for relative-price scaling -- instead of
    # re-deriving that math here.
    ordered = sorted(
        candles,
        key=lambda c: (
            c.utc_timestamp_in_minutes if c.utc_timestamp_in_minutes is not None else 0
        ),
    )
    bars: List[Bar] = []
    for i, c in enumerate(ordered):
        low = CTraderConnector._relative_price_to_real(c.low_raw, digits)
        high = (
            CTraderConnector._relative_price_to_real(c.low_raw + c.delta_high_raw, digits)
            if c.delta_high_raw is not None
            else low
        )
        close = (
            CTraderConnector._relative_price_to_real(c.low_raw + c.delta_close_raw, digits)
            if c.delta_close_raw is not None
            else low
        )
        timestamp: Optional[int] = (
            c.utc_timestamp_in_minutes * 60_000
            if c.utc_timestamp_in_minutes is not None
            else None
        )
        bars.append(Bar(index=i, high=high, low=low, close=close, timestamp=timestamp))
    return bars


def _wait_until_connected(connector: CTraderConnector, timeout: float = 15.0) -> defer.Deferred:
    # connector.connect() has no deferred for "now connected"; poll the
    # flag it already maintains. Glue for this orchestrator only, not
    # a new capability added to connector.py.
    d: defer.Deferred = defer.Deferred()
    elapsed = [0.0]
    interval = 0.1

    def _check():
        if connector.connected:
            lc.stop()
            if not d.called:
                d.callback(None)
            return
        elapsed[0] += interval
        if elapsed[0] >= timeout:
            lc.stop()
            if not d.called:
                d.errback(TimeoutError("Timed out waiting to connect"))

    lc = task.LoopingCall(_check)
    lc.start(interval, now=True)
    return d


@defer.inlineCallbacks
def _verify(
    market: MarketService,
    symbol_id: int,
    htf_timeframe: str,
    ltf_timeframe: str,
    direction: Direction,
    entry_zone: Tuple[float, float],
    htf_lookback: int,
    ltf_lookback: int,
    htf_limit: int,
    ltf_limit: int,
):
    symbol_info = yield market.get_symbol_info(symbol_id)
    htf_candles = yield market.get_candles(symbol_id, htf_timeframe, htf_limit)
    ltf_candles = yield market.get_candles(symbol_id, ltf_timeframe, ltf_limit)

    htf_bars = _candles_to_bars(htf_candles, symbol_info.digits)
    ltf_bars = _candles_to_bars(ltf_candles, symbol_info.digits)

    return validate_setup(
        htf_bars=htf_bars,
        ltf_bars=ltf_bars,
        direction=direction,
        entry_zone=entry_zone,
        htf_lookback=htf_lookback,
        ltf_lookback=ltf_lookback,
    )


def run(
    symbol_id: int,
    htf_timeframe: str,
    ltf_timeframe: str,
    direction: Direction,
    entry_zone: Tuple[float, float],
    htf_lookback: int,
    ltf_lookback: int,
    htf_limit: int = 200,
    ltf_limit: int = 500,
) -> None:
    """Connect, authenticate, verify one setup, print the result, exit."""
    connector = CTraderConnector()
    market = MarketService(connector)
    connector.connect()

    @defer.inlineCallbacks
    def _sequence():
        yield _wait_until_connected(connector)
        yield connector.application_auth(
            os.environ["CTRADER_CLIENT_ID"], os.environ["CTRADER_CLIENT_SECRET"]
        )
        yield connector.account_auth(
            int(os.environ["CTRADER_ACCOUNT_ID"]), os.environ["CTRADER_ACCESS_TOKEN"]
        )
        result = yield _verify(
            market,
            symbol_id,
            htf_timeframe,
            ltf_timeframe,
            direction,
            entry_zone,
            htf_lookback,
            ltf_lookback,
            htf_limit,
            ltf_limit,
        )
        if result.passed:
            print("PASS")
        else:
            print(f"FAIL: {result.failure_step.value}")

    def _fail(failure):
        print(f"FAIL: {failure.getErrorMessage()}")

    def _stop(_ignored=None):
        if reactor.running:
            reactor.stop()

    d = _sequence()
    d.addErrback(_fail)
    d.addBoth(_stop)
    reactor.run()


def _collect_inputs_from_env() -> dict:
    # The required inputs (symbol, timeframes, direction, entry zone,
    # lookbacks) collected from the environment. Connection secrets are
    # read separately, directly by run(), since they aren't part of
    # "what setup to verify."
    return dict(
        symbol_id=int(os.environ.get("SYMBOL_ID", "1")),
        htf_timeframe=os.environ.get("HTF_TIMEFRAME", "H4"),
        ltf_timeframe=os.environ.get("LTF_TIMEFRAME", "M5"),
        direction=Direction[os.environ.get("DIRECTION", "SELL")],
        entry_zone=(
            float(os.environ["ENTRY_ZONE_LOW"]),
            float(os.environ["ENTRY_ZONE_HIGH"]),
        ),
        htf_lookback=int(os.environ.get("HTF_LOOKBACK", "2")),
        ltf_lookback=int(os.environ.get("LTF_LOOKBACK", "2")),
    )


if __name__ == "__main__":
    run(**_collect_inputs_from_env())
