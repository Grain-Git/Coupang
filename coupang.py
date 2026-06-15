from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os, time, hmac, hashlib, requests
from dotenv import load_dotenv
load_dotenv()

from fastapi import Query
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import urllib.parse

from datetime import datetime, timedelta, timezone

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
    return {"status": "JRAIN Coupang API is running"}

@app.get("/health")
def health():
    return {
        "access_key": bool(COUPANG_ACCESS_KEY),
        "secret_key": bool(COUPANG_SECRET_KEY),
        "vendor_id": COUPANG_VENDOR_ID
    }

def make_auth(method, path, query=""):
    if not COUPANG_ACCESS_KEY or not COUPANG_SECRET_KEY or not COUPANG_VENDOR_ID:
        raise Exception("쿠팡 환경변수가 설정되지 않았습니다.")
    datetime = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    message = datetime + method + path + query

    signature = hmac.new(
        COUPANG_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return (
        "CEA algorithm=HmacSHA256, "
        f"access-key={COUPANG_ACCESS_KEY}, "
        f"signed-date={datetime}, "
        f"signature={signature}"
    )

@app.get("/api/coupang/rank-test")
def rank_test(
    keyword: str = Query(...),
    product_id: str = Query(...)
):
    encoded_keyword = urllib.parse.quote(keyword)

    url = f"https://www.coupang.com/np/search?q={encoded_keyword}&channel=user"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    res = requests.get(url, headers=headers, timeout=10)

    soup = BeautifulSoup(res.text, "html.parser")

    products = soup.select("li.search-product")

    result_list = []

    for index, item in enumerate(products, start=1):
        link = item.select_one("a")
        name = item.select_one(".name")

        href = link.get("href", "") if link else ""
        title = name.get_text(strip=True) if name else ""

        found = product_id in href

        result_list.append({
            "rank": index,
            "title": title,
            "href": "https://www.coupang.com" + href if href.startswith("/") else href,
            "matched": found
        })

        if found:
            return {
                "keyword": keyword,
                "product_id": product_id,
                "rank": index,
                "matched": True,
                "title": title,
                "url": "https://www.coupang.com" + href
            }

    return {
    "keyword": keyword,
    "product_id": product_id,
    "status_code": res.status_code,
    "html_length": len(res.text),
    "html_preview": res.text[:300],
    "products_count": len(products),
    "rank": None,
    "matched": False,
    "sample": result_list[:10]
    }


@app.get("/api/coupang/rank-playwright")
def rank_playwright(keyword: str, product_id: str):
    search_url = (
        "https://www.coupang.com/np/search"
        "?component=&q="
        + urllib.parse.quote(keyword)
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )

        context = browser.new_context(
            locale="ko-KR",
            viewport={"width": 1600, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0.0.0 Safari/537.36"
            )
        )

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = context.new_page()

        page.goto(
            search_url,
            wait_until="networkidle",
            timeout=60000
        )

        page.wait_for_timeout(5000)

        products = page.locator("li.search-product")
        count = products.count()

        sample = []

        for i in range(count):
            item = products.nth(i)
            text = item.inner_text()

            link = item.locator("a").first
            href = link.get_attribute("href") or ""

            rank = i + 1
            full_url = (
                "https://www.coupang.com" + href
                if href.startswith("/")
                else href
            )

            sample.append({
                "rank": rank,
                "title": text[:80],
                "url": full_url
            })

            if product_id in href or product_id in full_url or product_id in text:
                browser.close()
                return {
                    "keyword": keyword,
                    "product_id": product_id,
                    "matched": True,
                    "rank": rank,
                    "url": full_url,
                    "title": text[:120]
                }

        browser.close()

        return {
            "keyword": keyword,
            "product_id": product_id,
            "matched": False,
            "rank": None,
            "products_count": count,
            "sample": sample[:10]
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

    res = requests.get(url, headers=headers)

    try:
        result = res.json()
    except Exception:
        return {
            "error": "쿠팡 응답을 JSON으로 변환 실패",
            "status_code": res.status_code,
            "text": res.text
        }

    if result.get("code") != "SUCCESS":
        return {
            "error": "쿠팡 API 실패",
            "status_code": res.status_code,
            "result": result
        }

    raw_data = result.get("data", [])

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

    res = requests.get(url, headers=headers)
    return res.json()


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

    res = requests.get(url, headers=headers)
    result = res.json()

    return {
        "status_code": res.status_code,
        "data": result
    }

def get_kst_dates():
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
        query_parts = [
            f"paidDateFrom={paid_date_from}",
            f"paidDateTo={paid_date_to}"
        ]

        if next_token:
            query_parts.append(f"nextToken={next_token}")

        query = "&".join(query_parts)

        url = f"{DOMAIN}{path}?{query}"

        headers = {
            "Authorization": make_auth(method, path, query),
            "Content-Type": "application/json;charset=UTF-8"
        }

        res = requests.get(url, headers=headers, timeout=20)

        try:
            result = res.json()
        except Exception:
            return {
                "ok": False,
                "status_code": res.status_code,
                "error": "쿠팡 주문 응답 JSON 변환 실패",
                "text": res.text
            }

        if res.status_code >= 400:
            return {
                "ok": False,
                "status_code": res.status_code,
                "error": "쿠팡 주문 API 실패",
                "result": result
            }

        orders = result.get("data", []) or []
        all_orders.extend(orders)

        next_token = result.get("nextToken")

        if not next_token:
            break

    return {
        "ok": True,
        "orders": all_orders
    }


def summarize_orders(orders):
    total_quantity = 0
    total_sales_amount = 0
    order_count = len(orders)

    product_map = {}

    for order in orders:
        items = (
            order.get("orderItems")
            or order.get("data")
            or []
        )

        for item in items:
            qty = int(item.get("salesQuantity") or 0)
            price = int(float(item.get("unitSalesPrice") or item.get("salesPrice") or 0))
            amount = qty * price

            total_quantity += qty
            total_sales_amount += amount

            product_name = item.get("productName") or "상품명 없음"

            if product_name not in product_map:
                product_map[product_name] = {
                    "productName": product_name,
                    "quantity": 0,
                    "salesAmount": 0
                }

            product_map[product_name]["quantity"] += qty
            product_map[product_name]["salesAmount"] += amount

    top_products = sorted(
        product_map.values(),
        key=lambda x: x["quantity"],
        reverse=True
    )[:10]

    return {
        "orderCount": order_count,
        "quantity": total_quantity,
        "salesAmount": total_sales_amount,
        "topProducts": top_products
    }

@app.get("/api/coupang/sales-summary")
def get_coupang_sales_summary():
    today, month_start = get_kst_dates()

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
        "today": summarize_orders(today_result["orders"]),
        "month": summarize_orders(month_result["orders"])
    }