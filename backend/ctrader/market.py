from typing import List

from .connector import CTraderConnector, Quote, Candle, SymbolInfo

# Quote, Candle, SymbolInfo now live in connector.py (single source of truth
# for the real protobuf-derived data), and are re-exported here so existing
# imports of `from .market import Quote` etc. keep working.
__all__ = ["MarketService", "Quote", "Candle", "SymbolInfo"]


class MarketService:

    def __init__(self, connector: CTraderConnector) -> None:
        self.connector = connector

    def get_quote(self, symbol_id: int):
        # Returns a Twisted deferred resolving to a Quote. Subscribes once
        # per symbol and caches the latest value - safe to call repeatedly
        # for the same symbol, and the same subscription/cache is reused
        # if live streaming is built on top of this later.
        return self.connector.get_quote(symbol_id)

    def get_candles(self, symbol_id: int, timeframe: str, limit: int):
        # Returns a Twisted deferred resolving to a List[Candle].
        return self.connector.get_candles(symbol_id, timeframe, limit)

    def get_symbol_info(self, symbol_id: int):
        # Returns a Twisted deferred resolving to a SymbolInfo.
        return self.connector.get_symbol_info(symbol_id)
