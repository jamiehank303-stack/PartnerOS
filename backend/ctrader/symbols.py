from .connector import CTraderConnector, SymbolInfo

# SymbolInfo lives in connector.py (single source of truth for the real
# protobuf-derived data), re-exported here so existing imports of
# `from .symbols import SymbolInfo` keep working — same pattern as
# market.py (Quote/Candle/SymbolInfo) and positions.py (Position).
__all__ = ["SymbolService", "SymbolInfo"]


class SymbolService:
    """Thin wrapper around CTraderConnector.get_symbol_info() for the
    setup verification engine.

    This service intentionally contains no protocol logic of its own.
    All ProtoOASymbolByIdReq/ProtoOASymbolByIdRes handling, the official
    cent-scaled volume conversion (minVolume/maxVolume/stepVolume/
    lotSize), digits/pipPosition extraction, and MarketDataError
    translation on failure already live in CTraderConnector.get_symbol_info()
    (see connector.py) — connector.py remains the single source of truth
    for that behavior, so it is not duplicated here.
    """

    def __init__(self, connector: CTraderConnector) -> None:
        self.connector = connector

    def get_symbol_info(self, symbol_id: int):
        # Returns a Twisted deferred resolving to a SymbolInfo.
        # See CTraderConnector.get_symbol_info() for the request/response
        # handling this delegates to.
        return self.connector.get_symbol_info(symbol_id)
