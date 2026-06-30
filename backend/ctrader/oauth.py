import os
from dataclasses import dataclass
from typing import Optional

from ctrader_open_api import Auth

from .exceptions import AuthenticationError


@dataclass
class OAuthToken:
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str


def _get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise AuthenticationError(
            f"Required environment variable '{name}' is not set."
        )
    return value


class CTraderOAuth:

    def __init__(self) -> None:
        self.client_id: str = _get_required_env("CTRADER_CLIENT_ID")
        self.client_secret: str = _get_required_env("CTRADER_CLIENT_SECRET")
        self.redirect_uri: str = _get_required_env("CTRADER_REDIRECT_URI")

        self._auth = Auth(self.client_id, self.client_secret, self.redirect_uri)

    def get_authorization_url(self, scope: str = "trading") -> str:
        if scope not in ("trading", "accounts"):
            raise ValueError(
                "scope must be either 'trading' or 'accounts' "
                "as defined by the cTrader Open API."
            )

        return self._auth.getAuthUri(scope=scope)

    def exchange_code_for_token(self, auth_code: str) -> OAuthToken:
        if not auth_code:
            raise ValueError("Authorization code is required.")

        response = self._auth.getToken(auth_code)
        return self._parse_token_response(response)

    def refresh_access_token(self, refresh_token: str) -> OAuthToken:
        if not refresh_token:
            raise ValueError("Refresh token is required.")

        response = self._auth.refreshToken(refresh_token)
        return self._parse_token_response(response)

    def _parse_token_response(self, response: dict) -> OAuthToken:
        error_code: Optional[str] = response.get("errorCode")
        if error_code:
            description = response.get("description")
            raise AuthenticationError(
                f"cTrader OAuth request failed with errorCode={error_code}: "
                f"{description}"
            )

        access_token = response.get("accessToken")
        refresh_token = response.get("refreshToken")
        token_type = response.get("tokenType")
        expires_in = response.get("expiresIn")

        if not access_token or not refresh_token or expires_in is None:
            raise AuthenticationError(
                f"cTrader OAuth response is missing required fields: {response}"
            )

        return OAuthToken(
            access_token=access_token,
            token_type=token_type,
            expires_in=int(expires_in),
            refresh_token=refresh_token,
        )
