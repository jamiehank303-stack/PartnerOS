from dataclasses import dataclass

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

    def connect(self):
        print("Connecting to cTrader...")
        # WebSocket connection will go here
        self.connected = True

    def authorize(self):
        print("Authorizing account...")
        # OAuth token exchange will go here
        self.authorized = True

    def get_account(self):
        if not self.authorized:
            raise Exception("Not authorized")

        return self.account
