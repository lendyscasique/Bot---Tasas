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

SPREAD_SILENCIO = 7
SPREAD_MODERADO = 10
SPREAD_BUENO = 15

western_rate = None
last_update_id = None
p2p_ultimo_spread_alerta = 0

def get_binance(fiat):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    def fetch_side(side):
        payload = {"asset":"USDT","fiat":fiat,"merchantCheck":False,"page":1,"publisherType":None,"rows":10,"tradeType":side,"payTypes":[]}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            ads = r.json()["data"][:3]
            prices = [float(ad["adv"]["price"]) for ad in ads]
            return round(sum(prices)/len(prices), 2) if prices else None
        except:
            return None
    return fetch_side("SELL"), fetch_side("BUY")

def get_binance_banco(banco):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}

    pay_venta = [banco, "PagoMovil"] if banco in ["Banesco", "Mercantil"] else [banco]

    def fetch_venta():
        payload = {
            "asset": "USDT", "fiat": "VES",
            "merchantCheck": False, "page": 1,
            "publisherType": None, "rows": 10,
            "tradeType": "BUY",
            "payTypes": pay_venta,
            "transAmount": "1000"
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            ads = r.json()["data"][:3]
            prices = [float(ad["adv"]["price"]) for ad in ads]
            return round(sum(prices)/len(prices), 2) if prices else None
        except:
            return None

    def fetch_compra():
        payload = {
            "asset": "USDT", "fiat": "VES",
            "merchantCheck": False, "page": 1,
            "publisherType": None, "rows": 10,
            "tradeType": "SELL",
            "payTypes": [banco],
            "transAmount": "1000"
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            ads = r.json()["data"][:3]
            prices = [float(ad["adv"]["price"]) for ad in ads]
            return round(sum(prices)/len(prices), 2) if prices else None
        except:
            return None

    compra = fetch_compra()
    venta = fetch_venta()
    spread = round(venta - compra, 2) if venta and compra else 0
    return compra, venta, spread

def get_mejor_banco():
    ban_compra, ban_venta, ban_spread = get_binance_banco("Banesco")
    mer_compra, mer_venta, mer_spread = get_binance_banco("Mercantil")
    if mer_spread > ban_spread:
        return "Mercantil", mer_compra, mer_venta, mer_spread, ban_compra, ban_venta, ban_spread
    else:
        return "Banesco", ban_compra, ban_venta, ban_spread, mer_compra, mer_venta, mer_spread

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

def spread_emoji(spread):
    if spread >= SPREAD_BUENO:
        return "🚀"
    elif spread >= SPREAD_MODERADO:
        return "🟢"
    elif spread >= SPREAD_SILENCIO:
        return "🟡"
    else:
        return "🔴"

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)

def analizar_spread_p2p(mejor_banco, compra, venta, spread):
    global p2p_ultimo_spread_alerta
    if not compra or not venta:
        return
    if spread < SPREAD_SILENCIO:
        p2p_ultimo_spread_alerta = 0
        return
    if spread == p2p_ultimo_spread_alerta:
        return

    if spread >= SPREAD_BUENO:
        emoji = "🚀"
        nivel = "PREMIUM"
    elif spread >= SPREAD_MODERADO:
        emoji = "🟢"
        nivel = "BUENO"
    else:
        emoji = "🟡"
        nivel = "MODERADO"

    bs_recibidos = 100 * (1 - FEE_USDT_BS) * venta
    bs_pagados = 100 * compra
    fee_total_bs = (100 * FEE_USDT_BS * venta) + (100 * FEE_USDT_BS * compra)
    ganancia_bs = bs_recibidos - bs_pagados
    ganancia_usdt = round(ganancia_bs / compra, 4)

    msg  = f"{emoji} *SEÑAL P2P — {nivel}*\n\n"
    msg += f"🏦 Banco recomendado: *{mejor_banco}*\n\n"
    msg += f"Venta mercado:     `{fmt(venta)} Bs`\n"
    msg += f"Compra mercado:    `{fmt(compra)} Bs`\n"
    msg += f"Spread:            `{fmt(spread)} Bs`\n\n"
    msg += f"📊 *Estimado 100 USDT:*\n"
    msg += f"  Bs recibidos:    `{fmt(bs_recibidos)} Bs`\n"
    msg += f"  Bs pagados:      `{fmt(bs_pagados)} Bs`\n"
    msg += f"  Fee Binance:     `{fmt(fee_total_bs)} Bs`\n"
    msg += f"  Ganancia neta:   `{fmt(ganancia_bs)} Bs`\n"
    msg += f"  En USDT:         `~{fmt(ganancia_usdt, 4)} USDT`\n\n"
    msg += f"_Vende con {mejor_banco} + Pago Móvil_\n"
    msg += f"_Compra solo con {mejor_banco}_"
    enviar_telegram(msg)
    p2p_ultimo_spread_alerta = spread

def construir_mensaje(bs_compra, bs_venta, mejor_banco, m_compra, m_venta, m_spread, o_banco, o_compra, o_venta, o_spread, clp_compra, clp_venta, cop_compra, cop_venta, usd_clp, trm, bcv_usd, bcv_eur):
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

    # Binance Bs — ambos bancos
    if m_venta and m_compra:
        msg += f"🏦  *Binance {mejor_banco}* {spread_emoji(m_spread)}\n"
        msg += f"      Compra: `{fmt(m_compra)} Bs` | Venta: `{fmt(m_venta)} Bs`\n"
        msg += f"      Spread: `{fmt(m_spread)} Bs`\n\n"
    if o_venta and o_compra:
        msg += f"🏦  *Binance {o_banco}* {spread_emoji(o_spread)}\n"
        msg += f"      Compra: `{fmt(o_compra)} Bs` | Venta: `{fmt(o_venta)} Bs`\n"
        msg += f"      Spread: `{fmt(o_spread)} Bs`\n\n"

    msg += f"⭐ *Mejor opción: {mejor_banco}*\n\n"

    if clp_venta:
        msg += f"🔵  *Binance USDT/CLP*\n      Compra: `{fmt(clp_compra)} CLP` | Venta: `{fmt(clp_venta)} CLP`\n\n"
    if cop_venta:
        msg += f"🔵  *Binance USDT/COP*\n      Compra: `{fmt(cop_compra)} COP` | Venta: `{fmt(cop_venta)} COP`\n\n"
    if usd_clp:
        msg += f"🇨🇱  *Dólar Observado*\n      `{fmt(usd_clp)} CLP`\n\n"
    if western_rate:
        msg += f"🌍  *Western Unión*\n      `{fmt(western_rate, 4)} CLP/COP`\n\n"
    else:
        msg += f"🌍  *Western Unión*\n      _Envía /western TASA_\n\n"

    # Calcular con mejor banco
    limite_clp_bs = None
    limite_clp_cop = None
    if m_compra and m_venta and usd_clp:
        limite_clp_bs = (m_venta * (1 - FEE_USDT_BS)) / (usd_clp * (1 + FEE_USDT_CLP))
    if western_rate:
        limite_clp_cop = western_rate * (1 - FEE_WU)

    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"💱 *GSA CAMBIOS*\n"
    msg += f"_Calculado con {mejor_banco}_\n\n"
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
    if m_compra and m_venta:
        usd_bs_compra = round(((m_venta + m_compra) / 2) - MARGEN_BS, 2)
        msg += f"🔵  USD → Bs\n      `{fmt(m_venta)} Bs`\n\n"
        msg += f"🔵  Bs → USD\n      `{fmt(usd_bs_compra)} Bs`\n\n"
    if limite_clp_bs and limite_clp_cop:
        limite_bs_cop = limite_clp_cop / limite_clp_bs
        cop_bs = round(limite_bs_cop * (1 - FEE_COP_BS), 4)
        bs_cop = round(limite_bs_cop * (1 + FEE_COP_BS), 4)
        msg += f"🔵  COP → Bs\n      `{fmt(cop_bs, 4)}`\n\n"
        msg += f"🔵  Bs → COP\n      `{fmt(bs_cop, 4)}`\n\n"

    msg += f"📌 *Compra / Venta Pesos Colombianos*\n\n"
    if cop_venta and cop_compra:
        msg += f"🔵  USD → COP\n      `{fmt(cop_venta)} COP`\n\n"
        msg += f"🔵  COP → USD\n      `{fmt(cop_compra)} COP`\n\n"

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

            elif text.lower() == "/spread":
                mejor_banco, m_compra, m_venta, m_spread, o_banco, o_compra, o_venta, o_spread = get_mejor_banco()
                msg  = f"📊 *SPREAD ACTUAL*\n\n"
                msg += f"🏦 *{mejor_banco}* {spread_emoji(m_spread)}\n"
                msg += f"  Venta: `{fmt(m_venta)} Bs` | Compra: `{fmt(m_compra)} Bs`\n"
                msg += f"  Spread: `{fmt(m_spread)} Bs`\n\n"
                msg += f"🏦 *{o_banco}* {spread_emoji(o_spread)}\n"
                msg += f"  Venta: `{fmt(o_venta)} Bs` | Compra: `{fmt(o_compra)} Bs`\n"
                msg += f"  Spread: `{fmt(o_spread)} Bs`\n\n"
                msg += f"⭐ *Mejor opción: {mejor_banco}*\n\n"
                if m_spread >= SPREAD_SILENCIO:
                    bs_recibidos = 100 * (1 - FEE_USDT_BS) * m_venta
                    bs_pagados = 100 * m_compra
                    ganancia_bs = bs_recibidos - bs_pagados
                    ganancia_usdt = round(ganancia_bs / m_compra, 4)
                    msg += f"📊 *Por 100 USDT con {mejor_banco}:*\n"
                    msg += f"  Ganancia neta: `{fmt(ganancia_bs)} Bs`\n"
                    msg += f"  En USDT: `~{fmt(ganancia_usdt, 4)} USDT`\n"
                else:
                    msg += f"_Spread por debajo del mínimo operativo ({SPREAD_SILENCIO} Bs)_"
                enviar_telegram(msg)

            elif text.lower() == "/ayuda":
                msg  = "📋 *Comandos disponibles*\n\n"
                msg += "`/tasas` — Ver resumen completo de tasas\n"
                msg += "`/spread` — Ver spread P2P Banesco vs Mercantil\n"
                msg += "`/western TASA` — Actualizar Western Unión\n"
                msg += "`/ayuda` — Ver esta lista"
                enviar_telegram(msg)

    except Exception as e:
        print(f"Error check_commands: {e}")
    return pedir_tasas

def main():
    ultimo_envio_tasas = 0
    ultimo_check_p2p = 0

    while True:
        pedir_tasas = check_commands()
        ahora = time.time()

        if (ahora - ultimo_check_p2p) >= 300:
            mejor_banco, m_compra, m_venta, m_spread, _, _, _, _ = get_mejor_banco()
            analizar_spread_p2p(mejor_banco, m_compra, m_venta, m_spread)
            ultimo_check_p2p = ahora

        if pedir_tasas or (ahora - ultimo_envio_tasas) >= 1800:
            bs_compra, bs_venta = get_binance("VES")
            mejor_banco, m_compra, m_venta, m_spread, o_banco, o_compra, o_venta, o_spread = get_mejor_banco()
            clp_compra, clp_venta = get_binance("CLP")
            cop_compra, cop_venta = get_binance("COP")
            usd_clp = get_dolar_observado()
            trm = get_trm()
            bcv_usd, bcv_eur = get_bcv()
            msg = construir_mensaje(bs_compra, bs_venta, mejor_banco, m_compra, m_venta, m_spread, o_banco, o_compra, o_venta, o_spread, clp_compra, clp_venta, cop_compra, cop_venta, usd_clp, trm, bcv_usd, bcv_eur)
            enviar_telegram(msg)
            ultimo_envio_tasas = ahora
            print(f"Enviado — {datetime.datetime.now().strftime('%H:%M:%S')}")

        time.sleep(10)

if __name__ == "__main__":
    main()
