import re
import statistics
from bs4 import BeautifulSoup

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


def parse_int_text(value):
    """Convert strings like '1,234', '리뷰 2,001개', or '(98)' into an int."""
    if value is None:
        return 0
    found = re.findall(r"\d[\d,]*", str(value))
    if not found:
        return 0
    return int(found[0].replace(",", ""))


def parse_price_text(value):
    """Convert Coupang price text into an int KRW value."""
    if value is None:
        return 0
    found = re.findall(r"\d[\d,]*", str(value))
    if not found:
        return 0
    return int(found[-1].replace(",", ""))


def product_text_has_rocket(text):
    text = text or ""
    rocket_terms = [
        "로켓배송",
        "로켓와우",
        "로켓직구",
        "판매자로켓",
        "Rocket"
    ]
    return any(term in text for term in rocket_terms)


def extract_coupang_search_products(html_text, limit=36):
    """Parse public Coupang search HTML into product cards.

    This does not bypass login, CAPTCHA, or access controls. If Coupang returns
    a block/interstitial page, the product list will simply be empty.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    cards = soup.select("li.search-product")

    if not cards:
        cards = soup.select("[class*='search-product']")

    products = []

    for index, card in enumerate(cards[:limit], start=1):
        text = card.get_text(" ", strip=True)
        name_el = (
            card.select_one(".name")
            or card.select_one(".descriptions-inner")
            or card.select_one("[class*='name']")
        )
        price_el = (
            card.select_one(".price-value")
            or card.select_one("strong.price-value")
            or card.select_one("[class*='price']")
        )
        review_el = (
            card.select_one(".rating-total-count")
            or card.select_one("[class*='rating-total-count']")
            or card.select_one("[class*='review']")
        )
        link_el = card.select_one("a[href]")
        href = link_el.get("href") if link_el else ""

        if href and href.startswith("/"):
            href = "https://www.coupang.com" + href

        product_id = ""
        if href:
            match = re.search(r"/vp/products/(\d+)", href)
            if match:
                product_id = match.group(1)

        product_name = name_el.get_text(" ", strip=True) if name_el else text[:80]
        price = parse_price_text(price_el.get_text(" ", strip=True) if price_el else text)
        reviews = parse_int_text(review_el.get_text(" ", strip=True) if review_el else "")
        is_rocket = product_text_has_rocket(text)
        is_ad = "광고" in text[:30] or "AD" in text[:30].upper()

        if not product_name:
            continue

        products.append({
            "rank": index,
            "productId": product_id,
            "productName": product_name,
            "price": price,
            "reviewCount": reviews,
            "isRocket": is_rocket,
            "isAd": is_ad,
            "url": href
        })

    return products


@app.get("/api/coupang/search-analysis")
def search_analysis(keyword: str = Query(..., min_length=1), limit: int = Query(36, ge=1, le=72)):
    """Analyze public Coupang search results for sourcing competition signals.

    Frontend usage:
    /api/coupang/search-analysis?keyword=결로방지
    """
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://www.coupang.com/np/search?q={encoded_keyword}&channel=user"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.coupang.com/"
    }

    try:
        res = requests.get(url, headers=headers, timeout=20)
    except Exception as e:
        return {
            "success": False,
            "message": "쿠팡 검색 요청 실패",
            "detail": str(e)
        }

    if res.status_code >= 400:
        return {
            "success": False,
            "message": "쿠팡 검색 페이지 응답 실패",
            "status_code": res.status_code
        }

    products = extract_coupang_search_products(res.text, limit=limit)

    if not products:
        return {
            "success": False,
            "message": "쿠팡 검색 결과를 파싱하지 못했습니다. 차단/HTML 변경 가능성이 있습니다.",
            "keyword": keyword,
            "competitorCount": 0,
            "avgReviews": 0,
            "topReviews": 0,
            "rocketRatio": 0,
            "avgPrice": 0,
            "products": []
        }

    review_values = [p["reviewCount"] for p in products if p["reviewCount"] > 0]
    price_values = [p["price"] for p in products if p["price"] > 0]
    rocket_count = sum(1 for p in products if p["isRocket"])

    return {
        "success": True,
        "keyword": keyword,
        "source": "coupang_public_search",
        "checkedAt": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "competitorCount": len(products),
        "avgReviews": round(statistics.mean(review_values)) if review_values else 0,
        "topReviews": max(review_values) if review_values else 0,
        "rocketRatio": round((rocket_count / len(products)) * 100, 1) if products else 0,
        "avgPrice": round(statistics.mean(price_values)) if price_values else 0,
        "products": products[:20]
    }
