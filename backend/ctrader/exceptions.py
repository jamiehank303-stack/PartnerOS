class CTraderError(Exception):
    """Base exception for all cTrader module errors."""


class AuthenticationError(CTraderError):
    """Raised when authentication with the cTrader API fails."""


class AuthorizationError(CTraderError):
    """Raised when an account or application is not authorized."""


class ConnectionError(CTraderError):
    """Raised when a connection to the cTrader API fails or is lost."""


class MarketDataError(CTraderError):
    """Raised when market data (quotes, candles, symbol info) cannot be retrieved."""


class PositionError(CTraderError):
    """Raised when position data cannot be retrieved or is invalid."""


class AccountError(CTraderError):
    """Raised when account data cannot be retrieved or is invalid."""
