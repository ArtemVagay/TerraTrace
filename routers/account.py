from fastapi.routing import APIRouter

acc_router = APIRouter()

@acc_router.get("/account")
async def get_account():
    return {"message": "Это ваш аккаунт"}
