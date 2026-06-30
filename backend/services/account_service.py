from core.state import partner_state


class AccountService:

    @staticmethod
    def update_account(data):

        partner_state.balance = data.get("balance", 0)

        partner_state.equity = data.get("equity", 0)

        partner_state.margin = data.get("margin", 0)

        partner_state.free_margin = data.get("free_margin", 0)

        partner_state.currency = data.get("currency", "")
