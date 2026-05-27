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
        url = f"https://www.datos.gov.co/resource/32sa-8pi3.json?$where=vigenciadesde>='{ayer}T00:00:00.000'&$order=vigenciadesde DESC&$limit=1"
        data = requests.get(url, timeout=10).json()
        return float(data[0]["valor"]) if data else None
    except:
        return None

def get_bcv():
    try:
        url = "https://ve.dolarapi.com/v1/dolares"
        data = requests.get(url, timeout=10).json()
        usd = None
        eur = None
        for item in data:
            if item.get("fuente") == "oficial":
                usd = float(item.get("promedio", 0))
            if item.get("fuente") == "euro_oficial":
                eur = float(item.get("promedio", 0))
        return usd, eur
    except:
        return None, None

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id":TELEGRAM_CHAT_ID,"text":msg,"parse_mode":"Markdown"}, timeout=10)

def check_western_command():
    global western_rate
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        data = requests.get(url, timeout=10).json()
        for update in reversed(data.get("result", [])):
            msg = update.get("message", {}).get("text", "")
            if msg.lower().startswith("/western "):
                try:
                    western_rate = float(msg.split()[1].replace(",","."))
                except:
                    pass
                break
    except:
        pass

def main():
    while True:
        check_western_command()
        bs_compra, bs_venta = get_binance_usdt_bs()
        usd_clp = get_dolar_observado()
        trm = get_trm()
        bcv_usd, bcv_eur = get_bcv()
        ahora = datetime.datetime.now().strftime("%d/%m/%Y — %I:%M %p")

        msg = f"📊 *RESUMEN DE TASAS DE CAMBIO*\n"
        msg += f"📅 {ahora}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"🌎 *TASAS OFICIALES*\n\n"
        msg += "```\n"

        filas = []
        if trm:
            filas.append(("TRM", f"{trm:,.2f} COP"))
        if bcv_usd:
            filas.append(("USD/BCV", f"{bcv_usd:,.2f} Bs"))
        if bcv_eur:
            filas.append(("EUR/BCV", f"{bcv_eur:,.2f} Bs"))
        if bs_venta:
            filas.append(("Binance Venta", f"{bs_venta:,.2f} Bs"))
        if bs_compra:
            filas.append(("Binance Compra", f"{bs_compra:,.2f} Bs"))
        if usd_clp:
            filas.append(("Dolar Observado", f"{usd_clp:,.2f} CLP"))
        if western_rate:
            filas.append(("Western Union", f"{western_rate:,.4f} CLP/COP"))
        else:
            filas.append(("Western Union", "Enviar /western TASA"))

        ancho = max(len(f[0]) for f in filas) + 2
        for nombre, valor in filas:
            msg += f"{nombre:<{ancho}}{valor}\n"

        msg += "```\n"
        msg += "━━━━━━━━━━━━━━━━━━━━"

        enviar_telegram(msg)
        time.sleep(1800)

if __name__ == "__main__":
    main()
