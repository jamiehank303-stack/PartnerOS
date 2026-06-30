from authlib.integrations.starlette_client import OAuth
from config import CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET

oauth = OAuth()

oauth.register(
    name="ctrader",
    client_id=CTRADER_CLIENT_ID,
    client_secret=CTRADER_CLIENT_SECRET,
    authorize_url="https://id.ctrader.com/my/settings/openapi/grantingaccess/",
    access_token_url="https://openapi.ctrader.com/apps/token",
    client_kwargs={
        "scope": "trading"
    }
)
