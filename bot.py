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
last_update_id = None

def get_binance_usdt_bs():
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    def fetch_side(side):
        payload = {"asset":"USDT","fiat":"VES","merchantCheck":False,"page":1,"publisherType":None,"rows":5,"tradeType":side}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            prices = [float(ad["adv"]["price"]) for ad in r.json()["data"][:3]]
            return round(sum(prices)/len(prices), 2)
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
        r = requests.get("https://ve.dolarapi.com/v1/dolares/oficiales", timeout=10)
        data = r.json()
        usd = None
        eur = None
        for item in data:
            moneda = item.get("moneda", "").lower()
            if moneda == "usd":
                usd = float(item.get("promedio", 0))
            elif moneda == "eur":
                eur = float(item.get("promedio", 0))
        return usd, eur
    except:
        try:
            r = requests.get("https://api.bcv.org.ve/v1/tipos-de-cambio", timeout=10)
            data = r.json()
            usd = float(data.get("USD", 0)) or None
            eur = float(data.get("EUR", 0)) or None
            return usd, eur
        except:
            return None, None

def fmt(valor, decimales=2):
    return f"{valor:,.{decimales}f}"

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)

def construir_mensaje(bs_compra, bs_venta, usd_clp, trm, bcv_usd, bcv_eur):
    ahora = datetime.datetime.now().strftime("%d/%m/%Y — %I:%M %p")

    msg  = f"📊 *RESUMEN DE TASAS*\n"
    msg += f"📅 {ahora}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"🌎 *TASAS OFICIALES*\n\n"

    if trm:
        msg += f"🇨🇴  *TRM*\n      `{fmt(trm)} COP`\n\n"
    if bcv_usd:
        msg += f"🏦  *USD/BCV*\n      `{fmt(bcv_usd)} Bs`\n\n"
    if bcv_eur:
        msg += f"🏦  *EUR/BCV*\n      `{fmt(bcv_eur)} Bs`\n\n"
    if bs_venta:
        msg += f"🔵  *Binance Venta*\n      `{fmt(bs_venta)} Bs`\n\n"
    if bs_compra:
        msg += f"🔵  *Binance Compra*\n      `{fmt(bs_compra)} Bs`\n\n"
    if usd_clp:
        msg += f"🇨🇱  *Dólar Observado*\n      `{fmt(usd_clp)} CLP`\n\n"
    if western_rate:
        msg += f"🌍  *Western Unión*\n      `{fmt(western_rate, 4)} CLP/COP`\n\n"
    else:
        msg += f"🌍  *Western Unión*\n      _Envía /western TASA_\n\n"

    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"💱 *GSA CAMBIOS*\n\n"

    if bs_compra and bs_venta and usd_clp:
        limite_clp_bs = (bs_venta * (1 - FEE_USDT_BS)) / (usd_clp * (1 + FEE_USDT_CLP))
        clp_bs = round(limite_clp_bs * (1 - FEE_CLP_BS), 6)
        bs_clp = round(limite_clp_bs * (1 + FEE_BS_CLP), 6)
        tasa_bs = round(((bs_venta + bs_compra) / 2) - MARGEN_BS, 2)
        msg += f"📌 *Giros*\n\n"
        msg += f"🇨🇱➡️🇻🇪  CLP → Bs\n      `{fmt(clp_bs, 6)}`\n\n"
        msg += f"🇻🇪➡️🇨🇱  Bs → CLP\n      `{fmt(bs_clp, 6)}`\n\n"
        if usd_clp:
            msg += f"🇨🇱➡️🇺🇸  CLP → USD\n      `{fmt(usd_clp + SPREAD_CLP)} CLP`\n\n"
            msg += f"🇺🇸➡️🇨🇱  USD → CLP\n      `{fmt(usd_clp - SPREAD_CLP)} CLP`\n\n"

    if western_rate:
        limite_clp_cop = western_rate * (1 - FEE_WU)
        clp_cop = round(limite_clp_cop * (1 - FEE_CLP_COP), 4)
        cop_clp = round(limite_clp_cop * (1 + FEE_CLP_COP), 4)
        msg += f"🇨🇱➡️🇨🇴  CLP → COP\n      `{fmt(clp_cop, 4)}`\n\n"
        msg += f"🇨🇴➡️🇨🇱  COP → CLP\n      `{fmt(cop_clp, 4)}`\n\n"

        if bs_compra and bs_venta and usd_clp:
            limite_clp_bs = (bs_venta * (1 - FEE_USDT_BS)) / (usd_clp * (1 + FEE_USDT_CLP))
            limite_bs_cop = limite_clp_cop / limite_clp_bs
            bs_cop = round(limite_bs_cop * (1 - FEE_COP_BS), 4)
            cop_bs = round(limite_bs_cop * (1 + FEE_COP_BS), 4)
            msg += f"🇻🇪➡️🇨🇴  Bs → COP\n      `{fmt(bs_cop, 4)}`\n\n"
            msg += f"🇨🇴➡️🇻🇪  COP → Bs\n      `{fmt(cop_bs, 4)}`\n\n"

    msg += f"━━━━━━━━━━━━━━━━━━━━"
    return msg

def check_commands():
    global western_rate, last_update_id
    pedir_tasas = False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        params = {"timeout": 0}
        if last_update_id:
            params["offset"] = last_update_id + 1
        data = requests.get(url, params=params, timeout=10).json()
        updates = data.get("result", [])
        for update in updates:
            last_update_id = update["update_id"]
            text = (update.get("message", {}).get("text", "") or "").strip()
            if text.lower().startswith("/western"):
                parts = text.split()
                if len(parts) >= 2:
                    try:
                        western_rate = float(parts[1].replace(",", "."))
                        enviar_telegram(f"✅ *Western actualizada:* `{fmt(western_rate, 4)} CLP/COP`")
                    except:
                        enviar_telegram("⚠️ Formato inválido. Usa: `/western 4.1377`")
                else:
                    enviar_telegram("⚠️ Ejemplo: `/western 4.1377`")
            elif text.lower() == "/tasas":
                pedir_tasas = True
    except Exception as e:
        print(f"Error check_commands: {e}")
    return pedir_tasas

def main():
    ultimo_envio = 0
    while True:
        pedir_tasas = check_commands()
        ahora = time.time()
        if pedir_tasas or (ahora - ultimo_envio) >= 1800:
            bs_compra, bs_venta = get_binance_usdt_bs()
            usd_clp = get_dolar_observado()
            trm = get_trm()
            bcv_usd, bcv_eur = get_bcv()
            msg = construir_mensaje(bs_compra, bs_venta, usd_clp, trm, bcv_usd, bcv_eur)
            enviar_telegram(msg)
            ultimo_envio = ahora
            print(f"Enviado — {datetime.datetime.now().strftime('%H:%M:%S')}")
        time.sleep(10)

if __name__ == "__main__":
    main()
