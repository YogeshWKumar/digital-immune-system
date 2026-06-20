# test_baseline.py  ← this is your existing test suite in the repo
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_basic_order():
    response = client.post("/order", json={"product_id": 1, "quantity": 2})
    assert response.status_code == 200
    assert response.json()["total"] == 20.0

def test_save10_coupon():
    response = client.post("/order", json={
        "product_id": 1, "quantity": 2, "coupon": "SAVE10"
    })
    assert response.status_code == 200
    assert response.json()["total"] == 18.0

def test_save50_coupon():
    response = client.post("/order", json={
        "product_id": 2, "quantity": 4, "coupon": "SAVE50"
    })
    assert response.status_code == 200
    assert response.json()["total"] == 4.0