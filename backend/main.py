from fastapi import FastAPI

from api.account import router as account_router
from api.market import router as market_router

app = FastAPI(title="PartnerOS")

app.include_router(account_router)

app.include_router(market_router)


@app.get("/")
def home():

    return {

        "app": "PartnerOS",

        "status": "running"
    }
