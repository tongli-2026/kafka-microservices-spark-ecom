from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from cart_repository import CartRepository, CartItem
from schemas import CartItemRequest, CartResponse

router = APIRouter(prefix="/cart", tags=["cart"])

# Will be injected by main.py
cart_repo: CartRepository = None


@router.post("/{user_id}/items", status_code=status.HTTP_201_CREATED)
async def add_item(user_id: str, item: CartItemRequest) -> dict:
    """Add item to cart."""
    try:
        cart_item = CartItem(**item.model_dump())
        cart_repo.add_item(user_id, cart_item)
        return {"message": f"Item {item.product_id} added to cart"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{user_id}/items/{product_id}", status_code=status.HTTP_200_OK)
async def remove_item(user_id: str, product_id: str) -> dict:
    """Remove item from cart."""
    try:
        removed = cart_repo.remove_item(user_id, product_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found in cart",
            )
        return {"message": f"Item {product_id} removed from cart"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{user_id}", response_model=CartResponse)
async def get_cart(user_id: str) -> CartResponse:
    """Get user's cart."""
    try:
        cart = cart_repo.get_cart(user_id)
        return CartResponse(**cart)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{user_id}/checkout")
async def checkout(user_id: str) -> dict:
    """Initiate checkout - publishes cart.checkout_initiated event."""
    try:
        cart = cart_repo.get_cart(user_id)
        
        if not cart["items"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cart is empty",
            )

        # Cart will be cleared after event is published by consumer
        return {
            "message": "Checkout initiated",
            "cart": cart,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
