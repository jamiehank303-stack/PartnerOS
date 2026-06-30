import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from twisted.internet import defer, reactor

from ctrader_open_api import Client, TcpProtocol, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAAccountAuthReq,
    ProtoOATraderReq,
    ProtoOASymbolByIdReq,
    ProtoOASubscribeSpotsReq,
    ProtoOAUnsubscribeSpotsReq,
    ProtoOASpotEvent,
    ProtoOAGetTrendbarsReq,
    ProtoOAReconcileReq,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
    ProtoOATradeSide,
    ProtoOATrendbarPeriod,
)

from .exceptions import (
    AuthenticationError,
    ConnectionError,
    AccountError,
    MarketDataError,
    PositionError,
)

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Protocol-wide scaling constants.
#
# These are NOT per-symbol "precision" values and are NOT guesses — they
# are fixed conversion factors documented by Spotware independently of
# any individual symbol's digits/pipPosition:
#
#   PRICE_RELATIVE_SCALE: ProtoOASpotEvent.bid/ask (and ProtoOATrendbar
#   low/deltaOpen/deltaClose/deltaHigh) are transmitted as integers in a
#   fixed 1/100000 relative representation. The official tutorial is
#   explicit that the *only* correct way to obtain a real price is to
#   divide by 100000 and THEN round to the symbol's own `digits` (not
#   round to some other number of decimals).
#   Source: https://help.ctrader.com/open-api/symbol-data/
#       "you still have to transform the data into an actual price
#        value by dividing it by 100000 and rounding it to the symbol
#        digits"
#
#   VOLUME_CENTI_SCALE: ProtoOATradeData.volume, and ProtoOASymbol's
#   minVolume / maxVolume / stepVolume / lotSize, are all documented as
#   being expressed "in cents" (hundredths of a unit).
#   Source (.proto comments):
#   https://github.com/spotware/openapi-proto-messages/blob/main/OpenApiModelMessages.proto
#       "required int64 volume = 2; // Volume in cents (e.g. 1000 in
#        protocol means 10.00 units)."
#       "optional int64 maxVolume = 9; // Maximum allowed volume in
#        cents for an order with a symbol."
#       "optional int64 lotSize = 30; // Lot size of the Symbol (in
#        cents)."
#   Confirmed independently by Spotware staff on the Open API forum:
#   https://community.ctrader.com/forum/connect-api-support/38065/
#       "Open API returns Symbol min/max/step volumes in cents, you
#        have to divide it by 100 to get the volume in symbol quote
#        asset unit."
#
#   LEVERAGE_CENTI_SCALE: ProtoOATrader.leverageInCents is documented as
#   "Account leverage (e.g. If leverage = 1:50 then value = 5000)".
# ----------------------------------------------------------------------
PRICE_RELATIVE_SCALE = 100_000
VOLUME_CENTI_SCALE = 100
LEVERAGE_CENTI_SCALE = 100

# Application-level default for get_quote()'s wait on the first
# ProtoOASpotEvent. This is NOT a value defined by the Open API protocol
# (the spec does not promise a response SLA for spot subscriptions) — it
# exists purely so a caller's Deferred cannot hang forever if the
# subscription response is lost or the market produces no tick (e.g.
# market closed and no technical "first event" arrives for some
# reason). Callers can override it via get_quote(..., timeout=...).
DEFAULT_QUOTE_TIMEOUT_SECONDS = 10.0

# ----------------------------------------------------------------------
# Protobuf.extract() necessity — verified, not assumed.
#
# client.send()'s Deferred and the message passed into
# setMessageReceivedCallback() both deliver a generic ProtoMessage
# envelope (payloadType + opaque payload bytes), not the typed message.
# The official protocol guide spells out the required step explicitly:
#   "Use the payloadType field of the ProtoMessage object to find its
#    actual type. Via the Google Protobuf SDK, change the ProtoMessage
#    to an object of the needed ProtoOA... type."
#   Source: https://help.ctrader.com/open-api/sending-receiving-protobuf/
# `Protobuf.extract()` is the OpenApiPy SDK's implementation of exactly
# that decode step. Every official OpenApiPy sample (spotware/OpenApiPy
# main.py and ConsoleSample, referenced directly from the Open API
# forum) calls Protobuf.extract() on both event-callback messages and
# on the result handed to a request Deferred's success callback before
# touching any named field — e.g. "executionEvent = Protobuf.extract(message)"
# and "price_message = Protobuf.extract(message)" after a deferred
# resolves. It is therefore required, not optional, and is kept on
# every success/event handler in this file.
# ----------------------------------------------------------------------

# Official ProtoOATrendbarPeriod enum values (not hand-picked integers).
TRENDBAR_PERIOD: Dict[str, int] = {
    "M1": ProtoOATrendbarPeriod.M1,
    "M2": ProtoOATrendbarPeriod.M2,
    "M3": ProtoOATrendbarPeriod.M3,
    "M4": ProtoOATrendbarPeriod.M4,
    "M5": ProtoOATrendbarPeriod.M5,
    "M10": ProtoOATrendbarPeriod.M10,
    "M15": ProtoOATrendbarPeriod.M15,
    "M30": ProtoOATrendbarPeriod.M30,
    "H1": ProtoOATrendbarPeriod.H1,
    "H4": ProtoOATrendbarPeriod.H4,
    "H12": ProtoOATrendbarPeriod.H12,
    "D1": ProtoOATrendbarPeriod.D1,
    "W1": ProtoOATrendbarPeriod.W1,
    "MN1": ProtoOATrendbarPeriod.MN1,
}


@dataclass
class AccountInfo:
    account_id: int
    broker: Optional[str]
    currency: Optional[str]
    balance: float
    equity: Optional[float]
    leverage: Optional[float]


@dataclass
class Quote:
    symbol_id: int
    bid: Optional[float]
    ask: Optional[float]


@dataclass
class SymbolInfo:
    symbol_id: int
    digits: int
    pip_position: int
    lot_size: Optional[float]
    min_volume: Optional[float]
    max_volume: Optional[float]
    step_volume: Optional[float]


@dataclass
class Candle:
    period: int
    volume: int
    low_raw: int
    delta_open_raw: Optional[int]
    delta_close_raw: Optional[int]
    delta_high_raw: Optional[int]
    utc_timestamp_in_minutes: Optional[int]


@dataclass
class Position:
    position_id: int
    symbol_id: int
    side: str
    volume: float
    entry_price: Optional[float]
    current_price: Optional[float]
    profit: Optional[float]


# ----------------------------------------------------------------------
# Deferred-safety helpers.
#
# A twisted Deferred raises AlreadyCalledError if .callback()/.errback()
# is invoked on it more than once. The quote cache resolves pending
# Deferreds from an event-driven code path (_handle_spot_event) that is
# decoupled from where they were created (get_quote), so we guard every
# resolution site rather than relying on call-site bookkeeping to never
# double-fire a given Deferred.
# ----------------------------------------------------------------------
def _safe_callback(deferred: "defer.Deferred", result) -> None:
    if not deferred.called:
        deferred.callback(result)


def _safe_errback(deferred: "defer.Deferred", failure) -> None:
    if not deferred.called:
        deferred.errback(failure)


class CTraderConnector:

    def __init__(self):
        self.connected = False
        self.authorized = False
        self.account = None
        self.client: Optional[Client] = None
        self.ctid_trader_account_id: Optional[int] = None
        self._access_token: Optional[str] = None

        # Caches/state to support live quote streaming reuse.
        self._latest_quotes: Dict[int, Quote] = {}
        self._pending_quote_deferreds: Dict[int, List[defer.Deferred]] = {}
        self._subscribed_symbol_ids: set = set()

        # symbolId -> digits, populated by get_symbol_info(). Used to
        # round relative spot prices per the official conversion
        # procedure. We deliberately do NOT invent a default digits
        # value for symbols we haven't queried yet (see
        # _handle_spot_event).
        self._symbol_digits_cache: Dict[int, int] = {}

        # Dispatcher table for unsolicited/event-style messages that
        # arrive via _on_message_received rather than as a direct
        # response to a client.send() Deferred. Replaces the previous
        # single if/else "unknown packet" branch with a registry that
        # can be extended by adding entries here.
        self._event_dispatch: Dict[int, Callable] = {
            ProtoOASpotEvent().payloadType: self._handle_spot_event,
            # TODO: register handlers for other unsolicited event types
            # once their handling is implemented — e.g.
            # ProtoOAExecutionEvent, ProtoOAAccountDisconnectEvent,
            # ProtoOATraderUpdatedEvent, ProtoOAOrderErrorEvent. Do not
            # add entries here without verifying the exact payload
            # shape against the official message reference.
        }

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
        # Unsolicited messages (e.g. ProtoOASpotEvent) are pushed by the
        # server and are NOT correlated to a client.send() Deferred by
        # the SDK — they must be dispatched here. We look the handler
        # up by payloadType instead of an if/elif chain so new event
        # types can be added by registering them in self._event_dispatch
        # rather than growing this method.
        handler = self._event_dispatch.get(message.payloadType)
        if handler is not None:
            handler(message)
            return

        logger.warning(
            "No dispatcher registered for payloadType=%s (message type: %s)",
            message.payloadType,
            type(message),
        )

    def _handle_spot_event(self, message):
        parsed = Protobuf.extract(message)
        symbol_id = int(parsed.symbolId)
        digits = self._symbol_digits_cache.get(symbol_id)

        existing = self._latest_quotes.get(symbol_id)
        bid = (
            self._relative_price_to_real(parsed.bid, digits)
            if parsed.HasField("bid")
            else (existing.bid if existing else None)
        )
        ask = (
            self._relative_price_to_real(parsed.ask, digits)
            if parsed.HasField("ask")
            else (existing.ask if existing else None)
        )

        quote = Quote(symbol_id=symbol_id, bid=bid, ask=ask)
        self._latest_quotes[symbol_id] = quote

        pending = self._pending_quote_deferreds.pop(symbol_id, [])
        for deferred in pending:
            _safe_callback(deferred, quote)

    @staticmethod
    def _relative_price_to_real(raw: int, digits: Optional[int]) -> float:
        # Official conversion: divide the relative integer by 100000,
        # then round to the symbol's own `digits`.
        # https://help.ctrader.com/open-api/symbol-data/
        value = raw / PRICE_RELATIVE_SCALE
        if digits is None:
            # We don't yet know this symbol's `digits` (get_symbol_info
            # hasn't been called for it). Returning the unrounded
            # 1/100000-scaled value is the only verified behavior
            # available here; inventing a default digits count (e.g.
            # assuming 5) is not supported by the spec and would be a
            # guess.
            # TODO: round to symbol.digits once get_symbol_info(symbol_id)
            # has been called and the result is in _symbol_digits_cache.
            return value
        return round(value, digits)

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
        return [int(account.ctidTraderAccountId) for account in parsed.ctidTraderAccount]

    def _on_get_account_list_failure(self, failure):
        raise AuthenticationError(
            f"Fetching account list by access token failed: {failure}"
        )

    def account_auth(self, account_id: int, access_token: str):
        if not self.connected or self.client is None:
            raise ConnectionError(
                "Cannot perform account authentication before the client is connected"
            )

        self._access_token = access_token

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
        logger.info("Account %s has been authorized", self.ctid_trader_account_id)
        return response

    def _on_account_auth_failure(self, failure):
        self.authorized = False
        raise AuthenticationError(f"Account authentication failed: {failure}")

    def _require_authorized(self):
        if not self.authorized or self.client is None or self.ctid_trader_account_id is None:
            raise AuthenticationError("Connector is not account-authorized")

    # ------------------------------------------------------------------
    # get_account()
    # ------------------------------------------------------------------
    def get_account(self):
        self._require_authorized()

        request = ProtoOATraderReq()
        request.ctidTraderAccountId = self.ctid_trader_account_id

        deferred = self.client.send(request)
        deferred.addCallbacks(self._on_get_account_success, self._on_get_account_failure)
        return deferred

    def _on_get_account_success(self, response) -> AccountInfo:
        parsed = Protobuf.extract(response)
        trader = parsed.trader

        # ProtoOATrader.moneyDigits: "Specifies the exponent of the
        # monetary values. E.g. moneyDigits = 8 must be interpreted as
        # business value multiplied by 10^8, then real balance would be
        # 10053099944 / 10^8 = 100.53099944."
        # The field is optional with no documented default if unset;
        # we follow plain protobuf3 scalar semantics (0) rather than
        # inventing a value, but this has not been verified against a
        # live account where moneyDigits is absent.
        money_digits = trader.moneyDigits if trader.HasField("moneyDigits") else 0
        balance = trader.balance / (10 ** money_digits) if money_digits else float(trader.balance)

        account_info = AccountInfo(
            account_id=int(trader.ctidTraderAccountId),
            broker=trader.brokerName if trader.HasField("brokerName") else None,
            currency=None,  # TODO: requires ProtoOAAssetListReq to resolve depositAssetId
            balance=balance,
            equity=None,  # TODO: not provided by the API; must be derived from balance + open position PnL
            leverage=(
                trader.leverageInCents / LEVERAGE_CENTI_SCALE
                if trader.HasField("leverageInCents")
                else None
            ),
        )
        self.account = account_info
        return account_info

    def _on_get_account_failure(self, failure):
        raise AccountError(f"Fetching trader account data failed: {failure}")

    # ------------------------------------------------------------------
    # get_symbol_info()
    # ------------------------------------------------------------------
    def get_symbol_info(self, symbol_id: int):
        self._require_authorized()

        request = ProtoOASymbolByIdReq()
        request.ctidTraderAccountId = self.ctid_trader_account_id
        request.symbolId.append(symbol_id)

        deferred = self.client.send(request)
        deferred.addCallbacks(self._on_symbol_info_success, self._on_symbol_info_failure)
        return deferred

    def _on_symbol_info_success(self, response) -> SymbolInfo:
        parsed = Protobuf.extract(response)
        if not parsed.symbol:
            raise MarketDataError("Symbol not found in ProtoOASymbolByIdRes")

        symbol = parsed.symbol[0]
        symbol_id = int(symbol.symbolId)
        digits = int(symbol.digits)

        # Cache digits so spot-event price scaling can round correctly.
        self._symbol_digits_cache[symbol_id] = digits

        # lotSize / minVolume / maxVolume / stepVolume are documented as
        # being expressed in cents (hundredths of a unit), the same as
        # position/order volume — see VOLUME_CENTI_SCALE above.
        return SymbolInfo(
            symbol_id=symbol_id,
            digits=digits,
            pip_position=int(symbol.pipPosition),
            lot_size=(
                symbol.lotSize / VOLUME_CENTI_SCALE if symbol.HasField("lotSize") else None
            ),
            min_volume=(
                symbol.minVolume / VOLUME_CENTI_SCALE if symbol.HasField("minVolume") else None
            ),
            max_volume=(
                symbol.maxVolume / VOLUME_CENTI_SCALE if symbol.HasField("maxVolume") else None
            ),
            step_volume=(
                symbol.stepVolume / VOLUME_CENTI_SCALE if symbol.HasField("stepVolume") else None
            ),
        )

    def _on_symbol_info_failure(self, failure):
        raise MarketDataError(f"Fetching symbol info failed: {failure}")

    # ------------------------------------------------------------------
    # get_quote() - built on the official spot subscription so the same
    # subscription/cache can be reused for future live streaming.
    # ------------------------------------------------------------------
    def get_quote(self, symbol_id: int, timeout: float = DEFAULT_QUOTE_TIMEOUT_SECONDS):
        self._require_authorized()

        if symbol_id in self._latest_quotes:
            return defer.succeed(self._latest_quotes[symbol_id])

        deferred = defer.Deferred(canceller=self._make_quote_canceller(symbol_id))
        self._pending_quote_deferreds.setdefault(symbol_id, []).append(deferred)

        if symbol_id not in self._subscribed_symbol_ids:
            request = ProtoOASubscribeSpotsReq()
            request.ctidTraderAccountId = self.ctid_trader_account_id
            request.symbolId.append(symbol_id)

            subscribe_deferred = self.client.send(request)
            subscribe_deferred.addErrback(self._on_subscribe_spots_failure, symbol_id)
            self._subscribed_symbol_ids.add(symbol_id)

        # Bound the wait: if no ProtoOASpotEvent arrives within `timeout`
        # seconds, cancel the Deferred (invoking the canceller below to
        # clean up _pending_quote_deferreds) and fail with a
        # MarketDataError instead of hanging indefinitely.
        deferred.addTimeout(timeout, reactor, onTimeoutCancel=self._on_quote_timeout)
        return deferred

    def _make_quote_canceller(self, symbol_id: int):
        def _canceller(deferred: "defer.Deferred") -> None:
            pending = self._pending_quote_deferreds.get(symbol_id)
            if pending is None:
                return
            if deferred in pending:
                pending.remove(deferred)
            if not pending:
                self._pending_quote_deferreds.pop(symbol_id, None)

        return _canceller

    def _on_quote_timeout(self, result, timeout):
        # Translates the default CancelledError raised by
        # Deferred.addTimeout() into a MarketDataError consistent with
        # the rest of this connector's error handling.
        raise MarketDataError(
            f"Timed out after {timeout}s waiting for a ProtoOASpotEvent "
            "quote; the spot subscription response may have been lost "
            "or no tick was produced in time."
        )

    def _on_subscribe_spots_failure(self, failure, symbol_id: int):
        self._subscribed_symbol_ids.discard(symbol_id)
        pending = self._pending_quote_deferreds.pop(symbol_id, [])
        error = MarketDataError(f"Subscribing to spots for symbol {symbol_id} failed: {failure}")
        for deferred in pending:
            _safe_errback(deferred, error)

    # ------------------------------------------------------------------
    # unsubscribe_quote()
    #
    # Should spot subscriptions ever be unsubscribed? Yes. Per the
    # official docs, a subscription is a standing server-side resource
    # tied to (account, symbol) that keeps pushing ProtoOASpotEvent
    # traffic until explicitly cancelled:
    #   "Request to stop receiving ProtoOASpotEvents related to
    #    particular symbols. Unsubscription is useful to minimize
    #    traffic, especially during high volatility events."
    #   Source: https://help.ctrader.com/open-api/messages/
    #   "To unsubscribe from quotes data, you can always send the
    #    ProtoOAUnsubscribeSpotsReq message containing the symbolId and
    #    your ctidTraderAccountId."
    #   Source: https://help.ctrader.com/open-api/symbol-data/
    #
    # This connector only ever opportunistically subscribes (inside
    # get_quote) and never unsubscribes on its own, because it has no
    # way to know when a caller is actually done with a symbol_id —
    # that's a caller-level decision. Callers that no longer need live
    # updates for a symbol should call unsubscribe_quote() explicitly
    # to release the server-side subscription and stop the traffic.
    # ------------------------------------------------------------------
    def unsubscribe_quote(self, symbol_id: int):
        self._require_authorized()

        if symbol_id not in self._subscribed_symbol_ids:
            return defer.succeed(None)

        request = ProtoOAUnsubscribeSpotsReq()
        request.ctidTraderAccountId = self.ctid_trader_account_id
        request.symbolId.append(symbol_id)

        deferred = self.client.send(request)
        deferred.addCallbacks(
            lambda response: self._on_unsubscribe_spots_success(response, symbol_id),
            lambda failure: self._on_unsubscribe_spots_failure(failure, symbol_id),
        )
        return deferred

    def _on_unsubscribe_spots_success(self, response, symbol_id: int):
        self._subscribed_symbol_ids.discard(symbol_id)
        self._latest_quotes.pop(symbol_id, None)

        # Any Deferreds still waiting on a first quote for this symbol
        # will now never receive a ProtoOASpotEvent — fail them rather
        # than leaving them pending forever (they're also still
        # protected by their own addTimeout as a backstop).
        pending = self._pending_quote_deferreds.pop(symbol_id, [])
        error = MarketDataError(
            f"Spot subscription for symbol {symbol_id} was unsubscribed "
            "before a quote was received."
        )
        for deferred in pending:
            _safe_errback(deferred, error)

        logger.info("Unsubscribed from spot quotes for symbol %s", symbol_id)
        return response

    def _on_unsubscribe_spots_failure(self, failure, symbol_id: int):
        raise MarketDataError(f"Unsubscribing from spots for symbol {symbol_id} failed: {failure}")

    # ------------------------------------------------------------------
    # get_candles() - historical trend bars
    # ------------------------------------------------------------------
    def get_candles(self, symbol_id: int, timeframe: str, limit: int):
        self._require_authorized()

        if timeframe not in TRENDBAR_PERIOD:
            raise ValueError(
                f"Unknown timeframe '{timeframe}'. Valid values: {sorted(TRENDBAR_PERIOD)}"
            )

        requested_period = TRENDBAR_PERIOD[timeframe]

        request = ProtoOAGetTrendbarsReq()
        request.ctidTraderAccountId = self.ctid_trader_account_id
        request.symbolId = symbol_id
        request.period = requested_period
        request.count = limit
        # toTimestamp is optional per the official spec with no
        # documented default; defaulting to "now" is a client-side
        # design choice here, not a verified protocol default.
        request.toTimestamp = int(time.time() * 1000)

        deferred = self.client.send(request)
        deferred.addCallbacks(
            lambda response: self._on_get_candles_success(response, requested_period),
            self._on_get_candles_failure,
        )
        return deferred

    def _on_get_candles_success(self, response, requested_period: int) -> List[Candle]:
        parsed = Protobuf.extract(response)
        candles: List[Candle] = []
        for bar in parsed.trendbar:
            candles.append(
                Candle(
                    period=int(bar.period) if bar.HasField("period") else requested_period,
                    volume=int(bar.volume),
                    low_raw=int(bar.low) if bar.HasField("low") else None,
                    delta_open_raw=int(bar.deltaOpen) if bar.HasField("deltaOpen") else None,
                    delta_close_raw=int(bar.deltaClose) if bar.HasField("deltaClose") else None,
                    delta_high_raw=int(bar.deltaHigh) if bar.HasField("deltaHigh") else None,
                    utc_timestamp_in_minutes=(
                        int(bar.utcTimestampInMinutes) if bar.HasField("utcTimestampInMinutes") else None
                    ),
                )
            )
        return candles

    def _on_get_candles_failure(self, failure):
        raise MarketDataError(f"Fetching trendbars failed: {failure}")

    # ------------------------------------------------------------------
    # get_positions()
    # ------------------------------------------------------------------
    def get_positions(self):
        self._require_authorized()

        request = ProtoOAReconcileReq()
        request.ctidTraderAccountId = self.ctid_trader_account_id

        deferred = self.client.send(request)
        deferred.addCallbacks(self._on_get_positions_success, self._on_get_positions_failure)
        return deferred

    def _on_get_positions_success(self, response) -> List[Position]:
        parsed = Protobuf.extract(response)
        positions: List[Position] = []
        for pos in parsed.position:
            trade_side = pos.tradeData.tradeSide
            if trade_side == ProtoOATradeSide.BUY:
                side = "BUY"
            elif trade_side == ProtoOATradeSide.SELL:
                side = "SELL"
            else:
                # ProtoOATradeSide is a required field with only BUY/SELL
                # defined today, but protobuf does not guarantee an
                # unrecognized int can't appear (e.g. a future enum value
                # added server-side before this client is updated).
                # Silently mapping anything-not-BUY to SELL would
                # misreport the position's direction, so fail loudly
                # instead of guessing.
                raise PositionError(
                    f"Position {pos.positionId} has an unrecognized "
                    f"tradeSide value ({trade_side}); expected "
                    "ProtoOATradeSide.BUY or ProtoOATradeSide.SELL."
                )
            positions.append(
                Position(
                    position_id=int(pos.positionId),
                    symbol_id=int(pos.tradeData.symbolId),
                    side=side,
                    volume=pos.tradeData.volume / VOLUME_CENTI_SCALE,
                    entry_price=float(pos.price) if pos.HasField("price") else None,
                    current_price=None,  # TODO: requires live quote correlation
                    profit=None,  # TODO: requires ProtoOAGetPositionUnrealizedPnLReq
                )
            )
        return positions

    def _on_get_positions_failure(self, failure):
        raise PositionError(f"Fetching open positions failed: {failure}")
