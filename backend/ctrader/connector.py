import logging
import os
from dataclasses import dataclass
from typing import Optional

from ctrader_open_api import Client, TcpProtocol, EndPoints

logger = logging.getLogger(__name__)


@dataclass
class AccountInfo:
    account_id: int
    broker: str
    currency: str
    balance: float
    equity: float


class CTraderConnector:

    def __init__(self):
        self.connected = False
        self.authorized = False
        self.account = None
        self.client: Optional[Client] = None

    def connect(self):
        host_type = os.environ.get("CTRADER_HOST_TYPE", "demo").lower()
        host = (
            EndPoints.PROTOBUF_LIVE_HOST
            if host_type == "live"
            else EndPoints.PROTOBUF_DEMO_HOST
        )

        self.client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)

        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message_received)

        self.client.startService()

    def _on_connected(self, client):
        self.connected = True

    def _on_disconnected(self, client, reason):
        self.connected = False

    def _on_message_received(self, client, message):
        # TODO: implement message dispatch. Incoming Protobuf messages
        # (ProtoOAApplicationAuthRes, ProtoOAAccountAuthRes, ProtoOASpotEvent,
        # ProtoOAReconcileRes, etc.) need to be routed to the deferred/handler
        # that is waiting for that specific response type. Not implemented yet.
        logger.warning(
            "Message dispatch not implemented yet. Received message type: %s",
            type(message),
        )

    def authorize(self):
        if not self.connected or self.client is None:
            raise Exception("Cannot authorize before the client is connected")

        # TODO: perform official cTrader Open API Application Authentication here.
        # Build a ProtoOAApplicationAuthReq with clientId/clientSecret (from the
        # OAuth credentials), send it via self.client.send(applicationAuthReq),
        # and set self.authorized = True only once a ProtoOAApplicationAuthRes
        # is actually received (success, not assumed).
        raise NotImplementedError(
            "Application authentication via ProtoOAApplicationAuthReq is not implemented yet"
        )

    def get_account(self):
        if not self.authorized:
            raise Exception("Not authorized")

        return self.account

    def get_quote(self, symbol):
        raise NotImplementedError

    def get_candles(self, symbol, timeframe, limit):
        raise NotImplementedError

    def get_symbol_info(self, symbol):
        raise NotImplementedError

    def get_positions(self):
        raise NotImplementedError
