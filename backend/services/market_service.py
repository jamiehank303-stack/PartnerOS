from core.state import partner_state


class MarketService:

    @staticmethod
    def update_symbol(symbol, bid, ask):

        partner_state.symbols[symbol] = {

            "bid": bid,

            "ask": ask
        }
