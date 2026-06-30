from fastapi import APIRouter
from core.state import partner_state

router = APIRouter()


@router.get("/account")

def account():

    return {

        "connected": partner_state.connected,

        "authorized": partner_state.authorized,

        "balance": partner_state.balance,

        "equity": partner_state.equity,

        "margin": partner_state.margin,

        "free_margin": partner_state.free_margin,

        "currency": partner_state.currency
    }
