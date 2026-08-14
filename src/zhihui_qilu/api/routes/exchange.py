"""Exchange API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/exchange", tags=["exchange"])


class ExchangeRequest(BaseModel):
    user_id: str
    user_name: str
    product_id: str


def get_service(request: Request):
    return request.app.state.container.points_service


@router.get("/products")
async def get_products(request: Request) -> dict[str, Any]:
    """Get all available exchange products."""
    service = get_service(request)
    products = service.get_exchange_products()
    return {"success": True, "data": {"products": products}}


@router.get("/products/{product_id}")
async def get_product(product_id: str, request: Request) -> dict[str, Any]:
    """Get product details."""
    service = get_service(request)
    product = service.get_exchange_product(product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")
    return {"success": True, "data": {"product": product}}


@router.post("/redeem")
async def exchange_product(body: ExchangeRequest, request: Request) -> dict[str, Any]:
    """Exchange points for a product."""
    service = get_service(request)
    result = service.exchange_product(body.user_id, body.user_name, body.product_id)
    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error"))
    return {"success": True, "data": result, "message": result.get("message")}


@router.get("/user/{user_id}")
async def get_user_exchanges(user_id: str, request: Request) -> dict[str, Any]:
    """Get user exchange records."""
    service = get_service(request)
    records = service.get_user_exchanges(user_id)
    return {"success": True, "data": {"exchanges": records}}


@router.post("/claim/{exchange_id}")
async def claim_exchange(exchange_id: str, request: Request) -> dict[str, Any]:
    """Mark an exchange as claimed."""
    service = get_service(request)
    result = service.claim_exchange(exchange_id)
    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error"))
    return {"success": True, "message": result.get("message")}