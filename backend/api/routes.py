from fastapi import APIRouter

router = APIRouter()

@router.get("/status")
def status():
    return {
        "connected": False,
        "authorized": False
    }
