from dataclasses import dataclass
from typing import Optional

from connector import CTraderConnector


@dataclass
class AccountSnapshot:
    account_id: int
    broker_name: str
    balance: float
    equity: float
    margin: Optional[float]
    free_margin: Optional[float]
    currency: str
    leverage: Optional[float]
    connection_status: str


def _derive_connection_status(connector: CTraderConnector) -> str:
    if connector.connected and connector.authorized:
        return "connected"
    if connector.connected and not connector.authorized:
        return "connected_unauthorized"
    return "disconnected"


def get_account_snapshot(connector: CTraderConnector) -> AccountSnapshot:
    connection_status = _derive_connection_status(connector)

    account = connector.get_account()

    return AccountSnapshot(
        account_id=account.account_id,
        broker_name=account.broker,
        balance=account.balance,
        equity=account.equity,
        margin=None,
        free_margin=None,
        currency=account.currency,
        leverage=None,
        connection_status=connection_status,
    )
