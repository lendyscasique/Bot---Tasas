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
OBJETIVO_USDT_DIARIO = 5.0
SPREAD_MINIMO = 10
SPREAD_BUENO = 15
SPREAD_PREMIUM = 20

western_rate = None
last_update_id = None

p2p_operaciones_hoy = []
p2p_venta_abierta = None
p2p_ganancia_hoy_bs = 0
p2p_fees_hoy_usdt = 0
p2p_ultimo_spread_alerta = 0
p2p_ultima_fecha = None

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
    return fetch_side("BUY"), fetch_side("SELL")

def get_binance_banesco():
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    def fetch_side(side):
        payload = {"asset":"USDT","fiat":"VES","merchantCheck":False,"page":1,"publisherType":None,"rows":10,"tradeType":side,"payTypes":["Banesco"],"transAmount":"1000"}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            ads = r.json()["data"][:3]
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
        return fetch_side("1"), fetch_side("0")
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

def usdt_ganados_hoy():
    ban_compra, _ = get_binance_banesco()
    precio_ref = ban_compra if ban_compra else 737
    return round(p2p_ganancia_hoy_bs / precio_ref, 4) if precio_ref else 0

def resumen_diario():
    usdt_hoy = usdt_ganados_hoy()
    progreso = min(100, round((usdt_hoy / OBJETIVO_USDT_DIARIO) * 100, 1))
    barra = "█" * int(progreso / 10) + "░" * (10 - int(progreso / 10))
    msg  = f"📈 *RESUMEN DEL DÍA*\n\n"
    msg += f"Rotaciones:        {len(p2p_operaciones_hoy)}\n"
    msg += f"Ganancia neta:     `{fmt(p2p_ganancia_hoy_bs)} Bs`\n"
    msg += f"Fees totales:      `{fmt(p2p_fees_hoy_usdt, 4)} USDT`\n"
    msg += f"Ganancia en USDT:  `~{fmt(usdt_hoy, 4)} USDT`\n\n"
    msg += f"🎯 Objetivo {OBJETIVO_USDT_DIARIO} USDT: {progreso}%\n"
    msg += f"`{barra}`\n"
    return msg

def analizar_spread_p2p(ban_compra, ban_venta):
    global p2p_ultimo_spread_alerta
    if not ban_compra or not ban_venta:
        return
    spread = round(ban_venta - ban_compra, 2)
    if spread < SPREAD_MINIMO:
        return
    if spread == p2p_ultimo_spread_alerta:
        return
    if spread >= SPREAD_PREMIUM:
        emoji = "🚀"
        nivel = "PREMIUM"
    elif spread >= SPREAD_BUENO:
        emoji = "🟢"
        nivel = "BUENO"
    else:
        emoji = "🟡"
        nivel = "MODERADO"
    usdt_hoy = usdt_ganados_hoy()
    falta = max(0, OBJETIVO_USDT_DIARIO - usdt_hoy)
    bs_recibidos = 100 * (1 - 0.0025) * ban_venta
    bs_pagados = 100 * ban_compra
    ganancia_bs = bs_recibidos - bs_pagados - (0.05 * ban_compra)
    ganancia_usdt = round(ganancia_bs / ban_compra, 4)
    msg  = f"{emoji} *SEÑAL P2P — {nivel}*\n\n"
    msg += f"Spread actual:     `{fmt(spread)} Bs`\n"
    msg += f"Venta mercado:     `{fmt(ban_venta)} Bs`\n"
    msg += f"Compra mercado:    `{fmt(ban_compra)} Bs`\n\n"
    msg += f"📊 *Estimado 100 USDT:*\n"
    msg += f"  Bs recibidos:    `{fmt(bs_recibidos)} Bs`\n"
    msg += f"  Bs pagados:      `{fmt(bs_pagados)} Bs`\n"
    msg += f"  Ganancia neta:   `{fmt(ganancia_bs)} Bs`\n"
    msg += f"  En USDT:         `~{fmt(ganancia_usdt, 4)} USDT`\n\n"
    msg += f"🎯 *Objetivo del día:*\n"
    msg += f"  Logrado:  `{fmt(usdt_hoy, 4)} USDT`\n"
    msg += f"  Falta:    `{fmt(falta, 4)} USDT`\n\n"
    msg += f"_Registra con /vendi USDT PRECIO COMISION_"
    enviar_telegram(msg)
    p2p_ultimo_spread_alerta = spread

def construir_mensaje(bs_compra, bs_venta, ban_compra, ban_venta, clp_compra, clp_venta, cop_compra, cop_venta, bybit_compra, bybit_venta, usd_clp, trm, bcv_usd, bcv_eur):
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
    if ban_venta:
        msg += f"🟢  *Binance USDT/Bs (Banesco)*\n      Venta: `{fmt(ban_venta)} Bs` | Compra: `{fmt(ban_compra)} Bs`\n\n"
    elif bs_venta:
        msg += f"🔵  *Binance USDT/Bs*\n      Venta: `{fmt(bs_venta)} Bs` | Compra: `{fmt(bs_compra)} Bs`\n\n"
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
    bs_venta_calc = ban_venta if ban_venta else bs_venta
    bs_compra_calc = ban_compra if ban_compra else bs_compra
    limite_clp_bs = None
    limite_clp_cop = None
    if bs_compra_calc and bs_venta_calc and usd_clp:
        limite_clp_bs = (bs_venta_calc * (1 - FEE_USDT_BS)) / (usd_clp * (1 + FEE_USDT_CLP))
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
    if bs_compra_calc and bs_venta_calc:
        usd_bs_compra = round(((bs_venta_calc + bs_compra_calc) / 2) - MARGEN_BS, 2)
        msg += f"🔵  USD → Bs\n      `{fmt(bs_venta_calc)} Bs`\n\n"
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
    global p2p_venta_abierta, p2p_ganancia_hoy_bs, p2p_fees_hoy_usdt
    global p2p_operaciones_hoy, p2p_ultima_fecha
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
            elif text.lower().startswith("/vendi"):
                parts = text.split()
                if len(parts) >= 4:
                    try:
                        usdt = float(parts[1])
                        precio = float(parts[2].replace(",", "."))
                        comision = float(parts[3].replace(",", "."))
                        usdt_netos = usdt - comision
                        bs_recibidos = usdt_netos * precio
                        p2p_venta_abierta = {"usdt": usdt, "usdt_netos": usdt_netos, "precio_venta": precio, "comision": comision, "bs_recibidos": bs_recibidos, "hora": datetime.datetime.now().strftime("%H:%M")}
                        ban_compra, _ = get_binance_banesco()
                        spread_actual = round(precio - (ban_compra or 0), 2)
                        msg  = f"✅ *Venta registrada*\n\n"
                        msg += f"USDT vendidos:     `{fmt(usdt, 4)}`\n"
                        msg += f"Comisión Binance:  `{fmt(comision, 4)} USDT`\n"
                        msg += f"USDT liberados:    `{fmt(usdt_netos, 4)}`\n"
                        msg += f"Precio:            `{fmt(precio)} Bs`\n"
                        msg += f"Bs recibidos:      `{fmt(bs_recibidos)} Bs`\n\n"
                        msg += f"Compra actual:     `{fmt(ban_compra)} Bs`\n"
                        msg += f"Spread actual:     `{fmt(spread_actual)} Bs`\n\n"
                        msg += f"_Registra la compra con /compre USDT PRECIO COMISION_"
                        enviar_telegram(msg)
                    except:
                        enviar_telegram("⚠️ Formato inválido. Usa: `/vendi 20.24 742.90 0.05`")
                else:
                    enviar_telegram("⚠️ Ejemplo: `/vendi 20.24 742.90 0.05`")
            elif text.lower().startswith("/compre"):
                parts = text.split()
                if len(parts) >= 4 and p2p_venta_abierta:
                    try:
                        usdt = float(parts[1])
                        precio_compra = float(parts[2].replace(",", "."))
                        comision = float(parts[3].replace(",", "."))
                        usdt_netos = usdt - comision
                        bs_pagados = usdt * precio_compra
                        bs_recibidos = p2p_venta_abierta["bs_recibidos"]
                        ganancia_bs = bs_recibidos - bs_pagados
                        fees_totales_usdt = p2p_venta_abierta["comision"] + comision
                        p2p_ganancia_hoy_bs += ganancia_bs
                        p2p_fees_hoy_usdt += fees_totales_usdt
                        p2p_operaciones_hoy.append({"venta": p2p_venta_abierta["precio_venta"], "compra": precio_compra, "usdt": usdt, "ganancia_bs": ganancia_bs})
                        p2p_venta_abierta = None
                        usdt_hoy = usdt_ganados_hoy()
                        progreso = min(100, round((usdt_hoy / OBJETIVO_USDT_DIARIO) * 100, 1))
                        barra = "█" * int(progreso / 10) + "░" * (10 - int(progreso / 10))
                        msg  = f"✅ *Rotación completada*\n\n"
                        msg += f"Vendiste:          `{fmt(p2p_operaciones_hoy[-1]['venta'])} Bs`\n"
                        msg += f"Compraste:         `{fmt(precio_compra)} Bs`\n"
                        msg += f"USDT recibidos:    `{fmt(usdt_netos, 4)} USDT`\n"
                        msg += f"Bs recibidos:      `{fmt(bs_recibidos)} Bs`\n"
                        msg += f"Bs pagados:        `{fmt(bs_pagados)} Bs`\n"
                        msg += f"Fees totales:      `{fmt(fees_totales_usdt, 4)} USDT`\n"
                        msg += f"Ganancia neta:     `{fmt(ganancia_bs)} Bs`\n\n"
                        msg += f"🎯 Hoy: `{fmt(usdt_hoy, 4)} / {OBJETIVO_USDT_DIARIO} USDT` ({progreso}%)\n"
                        msg += f"`{barra}`"
                        enviar_telegram(msg)
                    except:
                        enviar_telegram("⚠️ Formato inválido. Usa: `/compre 20.19 737.00 0.05`")
                elif not p2p_venta_abierta:
                    enviar_telegram("⚠️ No hay venta abierta. Primero usa `/vendi USDT PRECIO COMISION`")
            elif text.lower() == "/resumen":
                enviar_telegram(resumen_diario())
            elif text.lower() == "/ayuda":
                msg  = "📋 *Comandos disponibles*\n\n"
                msg += "`/tasas` — Ver resumen de tasas\n"
                msg += "`/western TASA` — Actualizar Western\n"
                msg += "`/vendi USDT PRECIO COMISION` — Registrar venta P2P\n"
                msg += "`/compre USDT PRECIO COMISION` — Registrar compra P2P\n"
                msg += "`/resumen` — Ver resumen del día\n"
                msg += "`/ayuda` — Ver esta lista"
                enviar_telegram(msg)
    except Exception as e:
        print(f"Error check_commands: {e}")
    return pedir_tasas

def main():
    global p2p_operaciones_hoy, p2p_ganancia_hoy_bs, p2p_fees_hoy_usdt, p2p_ultima_fecha
    ultimo_envio_tasas = 0
    ultimo_check_p2p = 0

    while True:
        pedir_tasas = check_commands()
        ahora = time.time()

        hoy = datetime.date.today()
        if p2p_ultima_fecha != hoy:
            p2p_operaciones_hoy = []
            p2p_ganancia_hoy_bs = 0
            p2p_fees_hoy_usdt = 0
            p2p_ultima_fecha = hoy

        if (ahora - ultimo_check_p2p) >= 300:
            ban_compra, ban_venta = get_binance_banesco()
            analizar_spread_p2p(ban_compra, ban_venta)
            ultimo_check_p2p = ahora

        if pedir_tasas or (ahora - ultimo_envio_tasas) >= 1800:
            bs_compra, bs_venta = get_binance("VES")
            ban_compra, ban_venta = get_binance_banesco()
            clp_compra, clp_venta = get_binance("CLP")
            cop_compra, cop_venta = get_binance("COP")
            bybit_compra, bybit_venta = get_bybit_cop()
            usd_clp = get_dolar_observado()
            trm = get_trm()
            bcv_usd, bcv_eur = get_bcv()
            msg = construir_mensaje(bs_compra, bs_venta, ban_compra, ban_venta, clp_compra, clp_venta, cop_compra, cop_venta, bybit_compra, bybit_venta, usd_clp, trm, bcv_usd, bcv_eur)
            enviar_telegram(msg)
            ultimo_envio_tasas = ahora
            print(f"Enviado — {datetime.datetime.now().strftime('%H:%M:%S')}")

        time.sleep(10)

if __name__ == "__main__":
    main()
