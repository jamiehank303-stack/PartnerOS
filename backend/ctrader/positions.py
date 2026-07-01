from typing import List

from .connector import CTraderConnector, Position

# Position now lives in connector.py (single source of truth for the real
# protobuf-derived data), re-exported here so existing imports of
# `from .positions import Position` keep working.
__all__ = ["PositionService", "Position"]


class PositionService:

    def __init__(self, connector: CTraderConnector) -> None:
        self.connector = connector

    def get_open_positions(self):
        # Returns a Twisted deferred resolving to a List[Position].
        return self.connector.get_positions()
