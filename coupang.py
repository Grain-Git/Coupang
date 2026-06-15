from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import os
import time
import hmac
import hashlib
import requests
import urllib.parse
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://funny-mandazi-a35e41.netlify.app",
        "https://jrainstyle.com",
        "http://www.jrainstyle.com",
        "https://www.jrainstyle.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COUPANG_ACCESS_KEY = os.getenv("COUPANG_ACCESS_KEY")
COUPANG_SECRET_KEY = os.getenv("COUPANG_SECRET_KEY")
COUPANG_VENDOR_ID = os.getenv("COUPANG_VENDOR_ID")

DOMAIN = "https://api-gateway.coupang.com"


@app.get("/")
def home():
    return {
        "status": "JRAIN Coupang API is running"
    }


@app.get("/health")
def health():
    return {
        "access_key": bool(COUPANG_ACCESS_KEY),
        "secret_key": bool(COUPANG_SECRET_KEY),
        "vendor_id": COUPANG_VENDOR_ID
    }


def make_auth(method: str, path: str, query: str = ""):
    if not COUPANG_ACCESS_KEY or not COUPANG_SECRET_KEY or not COUPANG_VENDOR_ID:
        raise Exception("쿠팡 환경변수가 설정되지 않았습니다.")

    datetime_text = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    message = datetime_text + method + path + query

    signature = hmac.new(
        COUPANG_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return (
        "CEA algorithm=HmacSHA256, "
        f"access-key={COUPANG_ACCESS_KEY}, "
        f"signed-date={datetime_text}, "
        f"signature={signature}"
    )


def safe_json_response(res):
    try:
        return res.json()
    except Exception:
        return {
            "error": "JSON 변환 실패",
            "status_code": res.status_code,
            "text": res.text
        }


@app.get("/api/coupang/products")
def get_products():
    method = "GET"
    path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
    query = f"vendorId={COUPANG_VENDOR_ID}&nextToken=&maxPerPage=100"

    url = f"{DOMAIN}{path}?{query}"

    headers = {
        "Authorization": make_auth(method, path, query),
        "Content-Type": "application/json;charset=UTF-8"
    }

    res = requests.get(url, headers=headers, timeout=20)
    result = safe_json_response(res)

    if isinstance(result, dict) and result.get("code") != "SUCCESS":
        return {
            "error": "쿠팡 API 실패",
            "status_code": res.status_code,
            "result": result
        }

    raw_data = result.get("data", []) if isinstance(result, dict) else []

    products = []

    for p in raw_data:
        products.append({
            "id": p.get("sellerProductId"),
            "name": p.get("sellerProductName"),
            "status": p.get("statusName")
        })

    return products


@app.get("/api/coupang/products/{seller_product_id}/raw")
def get_product_raw(seller_product_id: int):
    method = "GET"
    path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}"
    query = ""

    url = f"{DOMAIN}{path}"

    headers = {
        "Authorization": make_auth(method, path, query),
        "Content-Type": "application/json;charset=UTF-8"
    }

    res = requests.get(url, headers=headers, timeout=20)

    return safe_json_response(res)


@app.get("/api/coupang/products/{seller_product_id}")
def get_product_detail(seller_product_id: int):
    method = "GET"
    path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}"
    query = ""

    url = f"{DOMAIN}{path}"

    headers = {
        "Authorization": make_auth(method, path, query),
        "Content-Type": "application/json;charset=UTF-8"
    }

    res = requests.get(url, headers=headers, timeout=20)
    result = safe_json_response(res)

    return {
        "status_code": res.status_code,
        "data": result
    }


def get_kst_range():
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)

    today = now.strftime("%Y%m%d")
    month_start = now.replace(day=1).strftime("%Y%m%d")

    return today, month_start


def fetch_rg_orders(paid_date_from: str, paid_date_to: str):
    method = "GET"
    path = f"/v2/providers/rg_open_api/apis/api/v1/vendors/{COUPANG_VENDOR_ID}/rg/orders"

    all_orders = []
    next_token = ""

    while True:
        query = f"paidDateFrom={paid_date_from}&paidDateTo={paid_date_to}"

        if next_token:
            query += f"&nextToken={next_token}"

        url = f"{DOMAIN}{path}?{query}"

        headers = {
            "Authorization": make_auth(method, path, query),
            "Content-Type": "application/json;charset=UTF-8"
        }

        res = requests.get(url, headers=headers, timeout=20)
        result = safe_json_response(res)

        if res.status_code >= 400:
            return {
                "ok": False,
                "status_code": res.status_code,
                "result": result
            }

        if isinstance(result, dict) and result.get("code") not in [None, "SUCCESS"]:
            return {
                "ok": False,
                "status_code": res.status_code,
                "result": result
            }

        orders = []

        if isinstance(result, dict):
            orders = result.get("data", []) or []

        all_orders.extend(orders)

        next_token = result.get("nextToken") if isinstance(result, dict) else None

        if not next_token:
            break

    return {
        "ok": True,
        "orders": all_orders
    }


def summarize_orders_by_product(orders):
    product_map = {}

    for order in orders:
        items = (
            order.get("orderItems")
            or order.get("items")
            or []
        )

        for item in items:
            product_name = (
                item.get("sellerProductName")
                or item.get("productName")
                or item.get("vendorItemName")
                or item.get("sellerProductItemName")
                or item.get("itemName")
                or "상품명 없음"
            )

            try:
                qty = int(item.get("salesQuantity") or item.get("quantity") or 0)
            except Exception:
                qty = 0

            try:
                unit_price = int(float(
                    item.get("unitSalesPrice")
                    or item.get("salesPrice")
                    or item.get("orderPrice")
                    or item.get("price")
                    or 0
                ))
            except Exception:
                unit_price = 0

            sales_amount = qty * unit_price

            if product_name not in product_map:
                product_map[product_name] = {
                    "productName": product_name,
                    "quantity": 0,
                    "salesAmount": 0
                }

            product_map[product_name]["quantity"] += qty
            product_map[product_name]["salesAmount"] += sales_amount

    products = sorted(
        product_map.values(),
        key=lambda x: x["quantity"],
        reverse=True
    )

    return {
        "orderCount": len(orders),
        "quantity": sum(p["quantity"] for p in products),
        "salesAmount": sum(p["salesAmount"] for p in products),
        "products": products
    }


@app.get("/api/coupang/sales-summary")
def get_sales_summary():
    today, month_start = get_kst_range()

    today_result = fetch_rg_orders(today, today)

    if not today_result.get("ok"):
        return {
            "success": False,
            "scope": "today",
            "error": today_result
        }

    month_result = fetch_rg_orders(month_start, today)

    if not month_result.get("ok"):
        return {
            "success": False,
            "scope": "month",
            "error": month_result
        }

    return {
        "success": True,
        "todayDate": today,
        "monthStart": month_start,
        "today": summarize_orders_by_product(today_result["orders"]),
        "month": summarize_orders_by_product(month_result["orders"])
    }