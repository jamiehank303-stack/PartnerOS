from dataclasses import dataclass
from typing import List, Optional

from .connector import CTraderConnector


@dataclass
class Position:
    position_id: int
    symbol: str
    side: str
    volume: float
    entry_price: float
    current_price: Optional[float]
    profit: Optional[float]


class PositionService:

    def __init__(self, connector: CTraderConnector) -> None:
        self.connector = connector

    def get_open_positions(self) -> List[Position]:
        return self.connector.get_positions()
