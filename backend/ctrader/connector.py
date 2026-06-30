import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from ctrader_open_api import Client, TcpProtocol, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAAccountAuthReq,
)

from .exceptions import AuthenticationError, ConnectionError

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
        self.ctid_trader_account_id: Optional[int] = None

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
        # (ProtoOASpotEvent, ProtoOAReconcileRes, ProtoOAExecutionEvent, etc.)
        # need to be routed to the deferred/handler that is waiting for that
        # specific response type. Not implemented yet.
        logger.warning(
            "Message dispatch not implemented yet. Received message type: %s",
            type(message),
        )

    def application_auth(self, client_id: str, client_secret: str):
        if not self.connected or self.client is None:
            raise ConnectionError(
                "Cannot perform application authentication before the client is connected"
            )

        request = ProtoOAApplicationAuthReq()
        request.clientId = client_id
        request.clientSecret = client_secret

        deferred = self.client.send(request)
        deferred.addCallbacks(
            self._on_application_auth_success,
            self._on_application_auth_failure,
        )
        return deferred

    def _on_application_auth_success(self, response):
        logger.info("Application authentication succeeded")
        return response

    def _on_application_auth_failure(self, failure):
        raise AuthenticationError(
            f"Application authentication failed: {failure}"
        )

    def get_account_list(self, access_token: str):
        if not self.connected or self.client is None:
            raise ConnectionError(
                "Cannot request account list before the client is connected"
            )

        request = ProtoOAGetAccountListByAccessTokenReq()
        request.accessToken = access_token

        deferred = self.client.send(request)
        deferred.addCallbacks(
            self._on_get_account_list_success,
            self._on_get_account_list_failure,
        )
        return deferred

    def _on_get_account_list_success(self, response) -> List[int]:
        parsed = Protobuf.extract(response)
        account_ids = [
            int(account.ctidTraderAccountId)
            for account in parsed.ctidTraderAccount
        ]
        return account_ids

    def _on_get_account_list_failure(self, failure):
        raise AuthenticationError(
            f"Fetching account list by access token failed: {failure}"
        )

    def account_auth(self, account_id: int, access_token: str):
        if not self.connected or self.client is None:
            raise ConnectionError(
                "Cannot perform account authentication before the client is connected"
            )

        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = account_id
        request.accessToken = access_token

        deferred = self.client.send(request)
        deferred.addCallbacks(
            self._on_account_auth_success,
            self._on_account_auth_failure,
        )
        return deferred

    def _on_account_auth_success(self, response):
        parsed = Protobuf.extract(response)
        self.ctid_trader_account_id = int(parsed.ctidTraderAccountId)
        self.authorized = True
        logger.info(
            "Account %s has been authorized", self.ctid_trader_account_id
        )
        return response

    def _on_account_auth_failure(self, failure):
        self.authorized = False
        raise AuthenticationError(
            f"Account authentication failed: {failure}"
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
