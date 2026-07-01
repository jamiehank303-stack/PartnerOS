from dataclasses import dataclass
from typing import Optional

from .connector import CTraderConnector


@dataclass
class AccountSnapshot:
    account_id: int
    broker_name: Optional[str]
    balance: float
    equity: Optional[float]
    margin: Optional[float]
    free_margin: Optional[float]
    currency: Optional[str]
    leverage: Optional[float]
    connection_status: str


def _derive_connection_status(connector: CTraderConnector) -> str:
    if connector.connected and connector.authorized:
        return "connected"
    if connector.connected and not connector.authorized:
        return "connected_unauthorized"
    return "disconnected"


def get_account_snapshot(connector: CTraderConnector):
    connection_status = _derive_connection_status(connector)

    # connector.get_account() now returns a Twisted deferred (real SDK call),
    # not a synchronous AccountInfo. We attach a callback that converts the
    # AccountInfo into an AccountSnapshot once the ProtoOATraderRes arrives.
    deferred = connector.get_account()

    def _to_snapshot(account_info) -> AccountSnapshot:
        return AccountSnapshot(
            account_id=account_info.account_id,
            broker_name=account_info.broker,
            balance=account_info.balance,
            equity=account_info.equity,  # None until unrealized PnL is implemented
            margin=None,  # not available from ProtoOATraderRes
            free_margin=None,  # not available from ProtoOATraderRes
            currency=account_info.currency,  # None until asset lookup is implemented
            leverage=account_info.leverage,
            connection_status=connection_status,
        )

    deferred.addCallback(_to_snapshot)
    return deferred
