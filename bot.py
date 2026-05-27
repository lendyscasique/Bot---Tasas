import requests
import json
import time
import datetime
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

FEE_USDT_CLP = 0.0020
FEE_USDT_BS = 0.0025
FEE_CLP_BS = 0.0550
FEE_CLP_COP = 0.0750
MARGEN_BS = 10
SPREAD_CLP = 50

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
        hoy = datetime.date.today().strftime("%Y-%m-%d")
        ayer = (datetime.date.today()-datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        url = f"https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx?user=&pass=&firstdate={ayer}&lastdate={hoy}&timeseries=F073.TCO.PRE.Z.D&function=GetSeries"
        data = requests.get(url, timeout=10).json()
        for e in reversed(data["Series"]["Obs"]):
            if e["value"] not in ("", None):
                return float(e["value"])
    except:
        return None

def get_trm():
    try:
        ayer = (datetime.date.today()-datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        url = f"https://www.datos.gov.co/resource/32sa-8pi3.json?$where=vigenciadesde>='{ayer}T00:00:00.000'&$order=vigenciadesde DESC&$limit=1"
        data = requests.get(url, timeout=10).json()
        return float(data[0]["valor"]) if data else None
    except:
        return None

def get_bcv():
    try:
        from bs4 import BeautifulSoup
        r = requests.get("https://www.bcv.org.ve/", timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        dolar = soup.find("div", id="dolar")
        if dolar:
            return float(dolar.find("strong").text.strip().replace(",","."))
    except:
        return None

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id":TELEGRAM_CHAT_ID,"text":msg,"parse_mode":"Markdown"}, timeout=10)

def main():
    while True:
        bs_compra, bs_venta = get_binance_usdt_bs()
        usd_clp = get_dolar_observado()
        trm = get_trm()
        bcv = get_bcv()
        ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        lineas = [f"📊 *Tasas Operativas — {ahora}*\n"]
        if usd_clp:
            lineas.append(f"🇨🇱 *USD/CLP*\n  Obs: `{usd_clp:,.0f}`\n  Compra: `{usd_clp-SPREAD_CLP:,.0f}` | Venta: `{usd_clp+SPREAD_CLP:,.0f}`\n")
        if bs_compra and bs_venta:
            tasa_bs = round(((bs_venta+bs_compra)/2)-MARGEN_BS,2)
            lineas.append(f"🇻🇪 *USDT/Bs*\n  Binance: `{bs_compra:,.2f}` / `{bs_venta:,.2f}`\n  Tasa propia: `{tasa_bs:,.2f}`\n")
            if usd_clp:
                limite = (bs_venta*(1+FEE_USDT_BS))/(usd_clp*(1+FEE_USDT_CLP))
                lineas.append(f"🔁 *CLP/Bs*\n  Límite: `{limite:.6f}`\n  CLP→Bs: `{limite*(1-FEE_CLP_BS):.6f}`\n  Bs→CLP: `{limite*(1+FEE_CLP_BS):.6f}`\n")
        if trm:
            lineas.append(f"🇨🇴 *TRM USD/COP*: `{trm:,.2f}`\n")
        if bcv:
            lineas.append(f"🏦 *BCV USD/Bs*: `{bcv:,.2f}`\n")
        enviar_telegram("\n".join(lineas))
        time.sleep(1800)

if __name__ == "__main__":
    main()
