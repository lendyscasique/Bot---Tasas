import requests
import time
import datetime
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

FEE_USDT_CLP = 0.0020
FEE_USDT_BS = 0.0025
FEE_CLP_BS = 0.0550
FEE_BS_CLP = 0.10
FEE_CLP_COP = 0.0750
MARGEN_BS = 10
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
                    western_rate = float(msg.split()[1])
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
        ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

        lineas = [f"📊 *Tasas — {ahora}*\n"]

        lineas.append("━━━ TASAS OFICIALES ━━━\n")
        if bs_compra and bs_venta:
            lineas.append(f"🔵 *Binance USDT/Bs*\n  Compra: `{bs_compra:,.2f}` | Venta: `{bs_venta:,.2f}`\n")
        if usd_clp:
            lineas.append(f"🇨🇱 *Dólar Observado*: `{usd_clp:,.2f}` CLP\n")
        if trm:
            lineas.append(f"🇨🇴 *TRM*: `{trm:,.2f}` COP\n")
        if bcv_usd:
            lineas.append(f"🏦 *BCV Dólar*: `{bcv_usd:,.2f}` Bs\n")
        if bcv_eur:
            lineas.append(f"🏦 *BCV Euro*: `{bcv_eur:,.2f}` Bs\n")
        if western_rate:
            lineas.append(f"🌍 *Western*: `{western_rate:,.4f}` CLP/COP\n")
        else:
            lineas.append(f"🌍 *Western*: _Envía /western TASA para actualizar_\n")

        lineas.append("\n━━━ GSA CAMBIOS — GIROS ━━━\n")
        if bs_compra and bs_venta and usd_clp:
            limite = (bs_venta*(1+FEE_USDT_BS))/(usd_clp*(1+FEE_USDT_CLP))
            clp_bs = round(limite*(1-FEE_CLP_BS), 6)
            bs_clp = round(limite*(1+FEE_BS_CLP), 6)
            lineas.append(f"  CLP → Bs: `{clp_bs:.6f}`\n  Bs → CLP: `{bs_clp:.6f}`\n")
        if western_rate:
            clp_cop = round(western_rate*(1-FEE_CLP_COP), 4)
            cop_clp = round(western_rate*(1+FEE_CLP_COP), 4)
            lineas.append(f"  CLP → COP: `{clp_cop:.4f}`\n  COP → CLP: `{cop_clp:.4f}`\n")
        if usd_clp:
            lineas.append(f"  CLP → USD: `{usd_clp+SPREAD_CLP:,.2f}`\n  USD → CLP: `{usd_clp-SPREAD_CLP:,.2f}`\n")

        enviar_telegram("\n".join(lineas))
        time.sleep(1800)

if __name__ == "__main__":
    main()
