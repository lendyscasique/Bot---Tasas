import requests
import time
import datetime
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

FEE_USDT_CLP = 0.002
FEE_USDT_BS = 0.0025
FEE_WU = 0.025
FEE_CLP_BS = 0.055
FEE_BS_CLP = 0.055
FEE_CLP_COP = 0.075
FEE_COP_BS = 0.055
MARGEN_BS = 30
SPREAD_CLP = 50

western_rate = None

def get_binance_usdt_bs():
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    def fetch_side(side):
        payload = {"asset":"USDT","fiat":"VES","merchantCheck":False,"page":1,"publisherType":None,"rows":5,"tradeType":side}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            prices = [float(ad["adv"]["price"]) for ad in r.json()["data"][:3]]
            return round(sum(prices)/len(prices),2)
        except:
            return None
    return fetch_side("BUY"), fetch_side("SELL")

def get_dolar_observado():
    try:
        url = "https://mindicador.cl/api/dolar"
        data = requests.get(url, timeout=10).json()
        return float(data["serie"][0]["valor"])
    except:
        return None

def get_trm():
    try:
        ayer = (datetime.date.today()-datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        url = f"https://www.datos.gov.c
