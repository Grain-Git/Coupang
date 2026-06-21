from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import os
import time
import hmac
import hashlib
import requests
import urllib.parse
import re
import statistics
from bs4 import BeautifulSoup
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
COUPANG_ORDER_STATUS = os.getenv("COUPANG_ORDER_STATUS", "ACCEPT")

DOMAIN = "https://api-gateway.coupang.com"


@app.get("/")
def home():
    return {"status": "JRAIN Coupang API is running"}


@app.get("/health")
def health():
    return {
        "access_key": bool(COUPANG_ACCESS_KEY),
        "secret_key": bool(COUPANG_SECRET_KEY),
        "vendor_id": COUPANG_VENDOR_ID,
        "order_status": COUPANG_ORDER_STATUS,
    }


def make_auth(method: str, path: str, query: str = ""):
    if not COUPANG_ACCESS_KEY or not COUPANG_SECRET_KEY or not COUPANG_VENDOR_ID:
        raise Exception("Missing Coupang environment variables.")

    datetime_text = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    message = datetime_text + method + path + query
    signature = hmac.new(
        COUPANG_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
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
            "error": "JSON parse failed",
            "status_code": res.status_code,
            "text": res.text,
        }


def is_coupang_success(result):
    """Accept Coupang success formats: SUCCESS, OK, 200, or empty successful data."""
    if not isinstance(result, dict):
        return True

    code = result.get("code")
    message = str(result.get("message") or "").upper()

    if code in [None, "SUCCESS", 200, "200"]:
        return True

    if message in ["OK", "SUCCESS"]:
        return True

    return False


@app.get("/api/coupang/products")
def get_products():
    method = "GET"
    path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
    query = f"vendorId={COUPANG_VENDOR_ID}&nextToken=&maxPerPage=100"
    url = f"{DOMAIN}{path}?{query}"
    headers = {
        "Authorization": make_auth(method, path, query),
        "Content-Type": "application/json;charset=UTF-8",
    }

    res = requests.get(url, headers=headers, timeout=20)
    result = safe_json_response(res)

    if res.status_code >= 400 or not is_coupang_success(result):
        return {
            "success": False,
            "error": "Coupang product API failed",
            "status_code": res.status_code,
            "result": result,
        }

    raw_data = result.get("data", []) if isinstance(result, dict) else []
    products = []

    for p in raw_data or []:
        products.append({
            "id": p.get("sellerProductId"),
            "sellerProductId": p.get("sellerProductId"),
            "name": p.get("sellerProductName"),
            "sellerProductName": p.get("sellerProductName"),
            "status": p.get("statusName"),
            "statusName": p.get("statusName"),
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
        "Content-Type": "application/json;charset=UTF-8",
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
        "Content-Type": "application/json;charset=UTF-8",
    }
    res = requests.get(url, headers=headers, timeout=20)
    result = safe_json_response(res)

    return {
        "status_code": res.status_code,
        "data": result,
    }


def get_kst_range():
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)

    return {
        "today": now.strftime("%Y%m%d"),
        "month_start": now.replace(day=1).strftime("%Y%m%d"),
        "hyphen_today": now.strftime("%Y-%m-%d"),
        "hyphen_month_start": now.replace(day=1).strftime("%Y-%m-%d"),
    }


def normalize_order_item(item):
    product_name = (
        item.get("sellerProductName")
        or item.get("productName")
        or item.get("vendorItemName")
        or item.get("sellerProductItemName")
        or item.get("itemName")
        or item.get("productTitle")
        or "상품명 없음"
    )

    try:
        qty = int(
            item.get("salesQuantity")
            or item.get("shippingCount")
            or item.get("quantity")
            or item.get("orderCount")
            or item.get("count")
            or 0
        )
    except Exception:
        qty = 0

    try:
        unit_price = int(float(
            item.get("unitSalesPrice")
            or item.get("salesPrice")
            or item.get("orderPrice")
            or item.get("salePrice")
            or item.get("price")
            or 0
        ))
    except Exception:
        unit_price = 0

    try:
        total_price = int(float(
            item.get("salesAmount")
            or item.get("totalPrice")
            or item.get("orderAmount")
            or 0
        ))
    except Exception:
        total_price = 0

    if total_price <= 0:
        total_price = qty * unit_price

    return product_name, qty, total_price


def get_order_items(order):
    for key in ["orderItems", "items", "itemList", "orderItemList", "orderSheetItems"]:
        value = order.get(key)
        if isinstance(value, list):
            return value
    return []


def get_order_key(order):
    return (
        order.get("orderId")
        or order.get("orderNo")
        or order.get("orderSheetId")
        or order.get("shipmentBoxId")
        or order.get("orderSheetNo")
        or order.get("receiptId")
        or str(order)[:120]
    )


def merge_order_results(*results):
    merged = []
    seen = set()
    sources = []
    errors = []

    for result in results:
        if not result:
            continue

        source = result.get("source", "unknown")
        if result.get("ok"):
            orders = result.get("orders") or []
            sources.append({
                "source": source,
                "count": len(orders),
            })
            for order in orders:
                key = get_order_key(order)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(order)
        else:
            errors.append(result)

    if merged:
        active_sources = [row["source"] for row in sources if row["count"] > 0]
        return {
            "ok": True,
            "source": "+".join(active_sources) if active_sources else "combined",
            "sources": sources,
            "orders": merged,
            "errors": errors,
        }

    for result in results:
        if result and result.get("ok"):
            return {
                "ok": True,
                "source": result.get("source", "empty"),
                "sources": sources,
                "orders": [],
                "errors": errors,
            }

    return {
        "ok": False,
        "sources": sources,
        "errors": errors,
    }


def summarize_orders_by_product(orders):
    product_map = {}
    order_ids = set()

    for order in orders:
        order_id = get_order_key(order)
        order_ids.add(order_id)

        for item in get_order_items(order):
            product_name, qty, sales_amount = normalize_order_item(item)

            if product_name not in product_map:
                product_map[product_name] = {
                    "productName": product_name,
                    "quantity": 0,
                    "salesAmount": 0,
                }

            product_map[product_name]["quantity"] += qty
            product_map[product_name]["salesAmount"] += sales_amount

    products = sorted(
        product_map.values(),
        key=lambda x: x["quantity"],
        reverse=True,
    )

    return {
        "orderCount": len(order_ids),
        "quantity": sum(p["quantity"] for p in products),
        "salesAmount": sum(p["salesAmount"] for p in products),
        "products": products,
    }


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
            "Content-Type": "application/json;charset=UTF-8",
        }

        res = requests.get(url, headers=headers, timeout=20)
        result = safe_json_response(res)

        if res.status_code >= 400 or not is_coupang_success(result):
            return {
                "ok": False,
                "source": "rocket_growth",
                "status_code": res.status_code,
                "result": result,
            }

        orders = result.get("data", []) if isinstance(result, dict) else []
        all_orders.extend(orders or [])

        next_token = result.get("nextToken") if isinstance(result, dict) else None
        if not next_token:
            break

    return {
        "ok": True,
        "source": "rocket_growth",
        "orders": all_orders,
    }


def fetch_ordersheets(created_at_from: str, created_at_to: str):
    method = "GET"
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{COUPANG_VENDOR_ID}/ordersheets"
    all_orders = []
    next_token = ""

    while True:
        query_parts = {
            "createdAtFrom": created_at_from,
            "createdAtTo": created_at_to,
            "status": COUPANG_ORDER_STATUS,
            "maxPerPage": "50",
        }
        if next_token:
            query_parts["nextToken"] = next_token

        query = urllib.parse.urlencode(query_parts)
        url = f"{DOMAIN}{path}?{query}"
        headers = {
            "Authorization": make_auth(method, path, query),
            "Content-Type": "application/json;charset=UTF-8",
        }

        res = requests.get(url, headers=headers, timeout=20)
        result = safe_json_response(res)

        if res.status_code >= 400 or not is_coupang_success(result):
            return {
                "ok": False,
                "source": "ordersheets",
                "status_code": res.status_code,
                "result": result,
            }

        orders = []
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, list):
                orders = data
            elif isinstance(data, dict):
                orders = data.get("data", []) or data.get("content", []) or []
            else:
                orders = result.get("content", []) or []

        all_orders.extend(orders or [])

        next_token = ""
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, dict):
                next_token = data.get("nextToken") or ""
            else:
                next_token = result.get("nextToken") or ""

        if not next_token:
            break

    return {
        "ok": True,
        "source": "ordersheets",
        "orders": all_orders,
    }


def fetch_best_available_orders(range_info, scope):
    if scope == "today":
        rg_result = fetch_rg_orders(range_info["today"], range_info["today"])
        order_result = fetch_ordersheets(range_info["hyphen_today"], range_info["hyphen_today"])
        merged = merge_order_results(rg_result, order_result)
        if merged.get("ok"):
            return merged

        return {
            "ok": False,
            "scope": scope,
            "rocketGrowthError": rg_result,
            "ordersheetsError": order_result,
        }

    rg_result = fetch_rg_orders(range_info["month_start"], range_info["today"])
    order_result = fetch_ordersheets(range_info["hyphen_month_start"], range_info["hyphen_today"])
    merged = merge_order_results(rg_result, order_result)
    if merged.get("ok"):
        return merged

    return {
        "ok": False,
        "scope": scope,
        "rocketGrowthError": rg_result,
        "ordersheetsError": order_result,
    }


@app.get("/api/coupang/sales-summary")
def get_sales_summary():
    range_info = get_kst_range()

    today_result = fetch_best_available_orders(range_info, "today")
    if not today_result.get("ok"):
        return {
            "success": False,
            "scope": "today",
            "error": today_result,
        }

    month_result = fetch_best_available_orders(range_info, "month")
    if not month_result.get("ok"):
        return {
            "success": False,
            "scope": "month",
            "error": month_result,
        }

    return {
        "success": True,
        "todayDate": range_info["today"],
        "monthStart": range_info["month_start"],
        "todaySource": today_result.get("source"),
        "monthSource": month_result.get("source"),
        "todaySources": today_result.get("sources", []),
        "monthSources": month_result.get("sources", []),
        "today": summarize_orders_by_product(today_result["orders"]),
        "month": summarize_orders_by_product(month_result["orders"]),
    }


def normalize_date_param(value):
    """Accept YYYY-MM-DD or YYYYMMDD and return both formats."""
    text = str(value or "").strip()
    if re.fullmatch(r"\d{8}", text):
        return text, f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text.replace("-", ""), text
    raise ValueError("Date must be YYYY-MM-DD or YYYYMMDD.")


@app.get("/api/coupang/sales-range")
def get_sales_range(
    from_date: str = Query(None, alias="from"),
    to_date: str = Query(None, alias="to"),
):
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst)
    default_from = today.replace(day=1).strftime("%Y-%m-%d")
    default_to = today.strftime("%Y-%m-%d")

    try:
        compact_from, hyphen_from = normalize_date_param(from_date or default_from)
        compact_to, hyphen_to = normalize_date_param(to_date or default_to)
    except ValueError as e:
        return {
            "success": False,
            "message": str(e),
        }

    range_info = {
        "today": compact_to,
        "month_start": compact_from,
        "hyphen_today": hyphen_to,
        "hyphen_month_start": hyphen_from,
    }

    result = fetch_best_available_orders(range_info, "month")
    if not result.get("ok"):
        return {
            "success": False,
            "from": hyphen_from,
            "to": hyphen_to,
            "error": result,
        }

    return {
        "success": True,
        "from": hyphen_from,
        "to": hyphen_to,
        "source": result.get("source"),
        "sources": result.get("sources", []),
        "summary": summarize_orders_by_product(result["orders"]),
    }


def parse_int_text(value):
    if value is None:
        return 0
    found = re.findall(r"\d[\d,]*", str(value))
    if not found:
        return 0
    return int(found[0].replace(",", ""))


def parse_price_text(value):
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
        "Rocket",
    ]
    return any(term in text for term in rocket_terms)


def extract_coupang_search_products(html_text, limit=36):
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
            "url": href,
        })

    return products


@app.get("/api/coupang/search-analysis")
def search_analysis(keyword: str = Query(..., min_length=1), limit: int = Query(36, ge=1, le=72)):
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
        "Referer": "https://www.coupang.com/",
    }

    try:
        res = requests.get(url, headers=headers, timeout=20)
    except Exception as e:
        return {
            "success": False,
            "message": "Coupang search request failed.",
            "detail": str(e),
        }

    if res.status_code >= 400:
        return {
            "success": False,
            "message": "Coupang search page request failed.",
            "status_code": res.status_code,
        }

    products = extract_coupang_search_products(res.text, limit=limit)

    if not products:
        return {
            "success": False,
            "message": "Could not parse Coupang search results.",
            "keyword": keyword,
            "competitorCount": 0,
            "avgReviews": 0,
            "topReviews": 0,
            "rocketRatio": 0,
            "avgPrice": 0,
            "products": [],
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
        "products": products[:20],
    }
