from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# ── Feature flag ──────────────────────────────────────────────────────────────
# Developer toggles this to True when committing the new feature
DISCOUNT_ENGINE_ENABLED = True

# ── Data ──────────────────────────────────────────────────────────────────────
products = {
    1: {"name": "Book", "price": 10.0, "stock": 5},
    2: {"name": "Pen",  "price": 2.0,  "stock": 10},
}

class OrderRequest(BaseModel):
    product_id: int
    quantity: int
    coupon: Optional[str] = None

# ── Business logic ────────────────────────────────────────────────────────────
def calculate_price(price: float, quantity: int, coupon: Optional[str]) -> float:
    if DISCOUNT_ENGINE_ENABLED:
        if coupon == "SAVE10":
            return round(price * quantity * 0.9, 2)  # Changed to apply 10% discount correctly
        elif coupon == "SAVE50":
            total_price = price * quantity  # Store total price for comparison
            return round(total_price - 50, 2) if total_price > 50 else round(total_price, 2)  # Changed to ensure 50 discount is applied correctly
    return round(price * quantity, 2)

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/order")
def place_order(req: OrderRequest):
    if req.product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    product = products[req.product_id]
    total = calculate_price(product["price"], req.quantity, req.coupon)
    return {
        "product": product["name"],
        "quantity": req.quantity,
        "total": total,
        "status": "confirmed"
    }

@app.get("/health")
def health():
    return {"status": "ok"}