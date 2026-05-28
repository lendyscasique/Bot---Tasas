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

def get_binance(fiat):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    def fetch_side(side, pay_types=None, max_amount=None):
        payload = {
            "asset": "USDT",
            "fiat": fiat,
            "merchantCheck": False,
            "page": 1,
            "publisherType": None,
            "rows": 10,
            "tradeType": side,
            "payTypes": pay_types or []
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            ads = r.json()["data"]
            if max_amount:
                ads = [ad for ad in ads if float(ad["adv"]["minSingleTransAmount"]) <= max_amount]
            ads = ads[:3]
            prices = [float(ad["adv"]["price"]) for ad in ads]
            return round(sum(prices)/len(prices), 2) if prices else None
        except:
            return None
    return fetch_side("BUY"), fetch_side("SELL")

def get_binance_banesco():
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    def fetch_side(side):
        payload = {
            "asset": "USDT",
            "fiat": "VES",
            "merchantCheck": False,
            "page": 1,
            "publisherType": None,
            "rows": 20,
            "tradeType": side,
            "payTypes": ["Banesco"]
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            ads = r.json()["data"]
            ads = [ad for ad in ads if float(ad["adv"]["minSingleTransAmount"]) <= 1000]
            ads = ads[:3]
            prices = [float(ad["adv"]["price"]) for ad in ads]
            return round(sum(prices)/len(prices), 2) if prices else None
        except:
            return None
    return fetch_side("BUY"), fetch_side("SELL")

def get_bybit_cop():
    try:
        url = "https://api2.bybit.com/fiat/otc/item/online"
        headers = {"Content-Type": "application/json"}
        def fetch_side(side):
            payload = {"tokenId":"USDT","currencyId":"COP","payment":[],"side":side,"size":"5","page":"1","amount":""}
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            items = r.json()["result"]["items"][:3]
            prices = [float(item["price"]) for item in items]
            return round(sum(prices)/len(prices), 2)
        compra = fetch_side("1")
        venta = fetch_side("0")
        return compra, venta
    except:
        return None, None

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
        url = "https://ve.dolarapi.com/v1/dolares/oficiales"
        data = requests.get(url, timeout=10).json()
        usd = None
        eur = None
        for item in data:
            moneda = item.get("moneda", "").lower()
            if moneda == "usd":
                usd = float(item.get("promedio", 0))
            elif moneda == "eur":
                eur = float(item.get("promedio", 0))
        if not eur:
            url2 = "https://ve.dolarapi.com/v1/dolares/euro"
            data2 = requests.get(url2, timeout=10).json()
            eur = float(data2.get("promedio", 0)) or None
        return usd, eur
    except:
        return None, None

def fmt(valor, decimales=2):
    return f"{valor:,.{decimales}f}"

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)

def construir_mensaje(bs_compra, bs_venta, clp_compra, clp_venta, cop_compra, cop_venta, bybit_compra, bybit_venta, usd_clp, trm, bcv_usd, bcv_eur):
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
        msg += f"🔵  *Binance USDT/Bs*\n      Venta: `{fmt(bs_venta)} Bs` | Compra: `{fmt(bs_compra)} Bs`\n\n"
    if ban_venta:
        msg += f"🟢  *Binance Banesco ≤1000*\n      Venta: `{fmt(ban_venta)} Bs` | Compra: `{fmt(ban_compra)} Bs`\n\n"
    if clp_venta:
        msg += f"🔵  *Binance USDT/CLP*\n      Venta: `{fmt(clp_venta)} CLP` | Compra: `{fmt(clp_compra)} CLP`\n\n"
    if cop_venta:
        msg += f"🔵  *Binance USDT/COP*\n      Venta: `{fmt(cop_venta)} COP` | Compra: `{fmt(cop_compra)} COP`\n\n"
    if bybit_venta:
        msg += f"🟠  *Bybit USDT/COP*\n      Venta: `{fmt(bybit_venta)} COP` | Compra: `{fmt(bybit_compra)} COP`\n\n"
    if usd_clp:
        msg += f"🇨🇱  *Dólar Observado*\n      `{fmt(usd_clp)} CLP`\n\n"
    if western_rate:
        msg += f"🌍  *Western Unión*\n      `{fmt(western_rate, 4)} CLP/COP`\n\n"
    else:
        msg += f"🌍  *Western Unión*\n      _Envía /western TASA_\n\n"

    limite_clp_bs = None
    limite_clp_cop = None
    if bs_compra and bs_venta and usd_clp:
        limite_clp_bs = (bs_venta * (1 - FEE_USDT_BS)) / (usd_clp * (1 + FEE_USDT_CLP))
    if western_rate:
        limite_clp_cop = western_rate * (1 - FEE_WU)

    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"💱 *GSA CAMBIOS*\n\n"
    msg += f"📌 *Giros*\n\n"

    if limite_clp_bs:
        clp_bs = round(limite_clp_bs * (1 - FEE_CLP_BS), 6)
        bs_clp = round(limite_clp_bs * (1 + FEE_BS_CLP), 6)
        msg += f"🇨🇱➡️🇻🇪  CLP → Bs\n      `{fmt(clp_bs, 6)}`\n\n"
        msg += f"🇻🇪➡️🇨🇱  Bs → CLP\n      `{fmt(bs_clp, 6)}`\n\n"

    if limite_clp_cop:
        clp_cop = round(limite_clp_cop * (1 - FEE_CLP_COP), 4)
        cop_clp = round(limite_clp_cop * (1 + FEE_CLP_COP), 4)
        msg += f"🇨🇱➡️🇨🇴  CLP → COP\n      `{fmt(clp_cop, 4)}`\n\n"
        msg += f"🇨🇴➡️🇨🇱  COP → CLP\n      `{fmt(cop_clp, 4)}`\n\n"

    if usd_clp:
        msg += f"🇨🇱➡️🇺🇸  CLP → USD\n      `{fmt(usd_clp + SPREAD_CLP)} CLP`\n\n"
        msg += f"🇺🇸➡️🇨🇱  USD → CLP\n      `{fmt(usd_clp - SPREAD_CLP)} CLP`\n\n"

    msg += f"📌 *Compra / Venta Bolívares*\n\n"

    if bs_compra and bs_venta:
        usd_bs_compra = round(((bs_venta + bs_compra) / 2) - MARGEN_BS, 2)
        msg += f"🔵  USD → Bs\n      `{fmt(bs_venta)} Bs`\n\n"
        msg += f"🔵  Bs → USD\n      `{fmt(usd_bs_compra)} Bs`\n\n"

    if limite_clp_bs and limite_clp_cop:
        limite_bs_cop = limite_clp_cop / limite_clp_bs
        cop_bs = round(limite_bs_cop * (1 - FEE_COP_BS), 4)
        bs_cop = round(limite_bs_cop * (1 + FEE_COP_BS), 4)
        msg += f"🔵  COP → Bs\n      `{fmt(cop_bs, 4)}`\n\n"
        msg += f"🔵  Bs → COP\n      `{fmt(bs_cop, 4)}`\n\n"

    msg += f"📌 *Compra / Venta Pesos Colombianos*\n\n"

    if bybit_venta and bybit_compra:
        msg += f"🟠  USD → COP\n      `{fmt(bybit_compra)} COP`\n\n"
        msg += f"🟠  COP → USD\n      `{fmt(bybit_venta)} COP`\n\n"
    elif cop_venta and cop_compra:
        msg += f"🔵  USD → COP\n      `{fmt(cop_compra)} COP`\n\n"
        msg += f"🔵  COP → USD\n      `{fmt(cop_venta)} COP`\n\n"

    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"📐 *LÍMITES OPERATIVOS*\n\n"

    if limite_clp_bs:
        msg += f"🔴  *Límite CLP/Bs*\n      `{fmt(limite_clp_bs, 6)}`\n\n"
    if limite_clp_cop:
        msg += f"🔴  *Límite CLP/COP*\n      `{fmt(limite_clp_cop, 4)}`\n\n"
        if limite_clp_bs:
            limite_bs_cop = limite_clp_cop / limite_clp_bs
            msg += f"🔴  *Límite Bs/COP*\n      `{fmt(limite_bs_cop, 4)}`\n\n"

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
        for update in data.get("result", []):
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
            bs_compra, bs_venta = get_binance("VES")
            clp_compra, clp_venta = get_binance("CLP")
            cop_compra, cop_venta = get_binance("COP")
            bybit_compra, bybit_venta = get_bybit_cop()
            usd_clp = get_dolar_observado()
            trm = get_trm()
            bcv_usd, bcv_eur = get_bcv()
            msg = construir_mensaje(bs_compra, bs_venta, clp_compra, clp_venta, cop_compra, cop_venta, bybit_compra, bybit_venta, usd_clp, trm, bcv_usd, bcv_eur)
            enviar_telegram(msg)
            ultimo_envio = ahora
            print(f"Enviado — {datetime.datetime.now().strftime('%H:%M:%S')}")
        time.sleep(10)

if __name__ == "__main__":
    main()
