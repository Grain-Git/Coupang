from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os, time, hmac, hashlib, requests
from dotenv import load_dotenv
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



@app.get("/api/coupang/products")
def get_products():

    method="GET"

    path="/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"

    query=f"vendorId={COUPANG_VENDOR_ID}&nextToken=&maxPerPage=100"

    url=f"{DOMAIN}{path}?{query}"

    headers={
        "Authorization":make_auth(method,path,query),
        "Content-Type":"application/json;charset=UTF-8"
    }

    res=requests.get(url,headers=headers)

    result=res.json()

    products=[]

    if result.get("code")=="SUCCESS":

        for p in result["data"]:

            products.append({

                "id":p["sellerProductId"],

                "name":p["sellerProductName"],

                "status":p["statusName"]

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