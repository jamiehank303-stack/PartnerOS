from dataclasses import dataclass
from typing import List, Optional

from .connector import CTraderConnector


@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]


@dataclass
class SymbolInfo:
    symbol: str
    digits: Optional[int]
    pip_size: Optional[float]
    contract_size: Optional[float]


class MarketService:

    def __init__(self, connector: CTraderConnector) -> None:
        self.connector = connector

    def get_quote(self, symbol: str) -> Quote:
        return self.connector.get_quote(symbol)

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        return self.connector.get_candles(symbol, timeframe, limit)

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        return self.connector.get_symbol_info(symbol)
