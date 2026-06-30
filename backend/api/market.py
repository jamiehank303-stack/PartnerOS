from fastapi import APIRouter
from core.state import partner_state

router = APIRouter()


@router.get("/market")

def market():

    return partner_state.symbols
