import requests
import time
import datetime
import os
import pytz

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CHILE_TZ = pytz.timezone("America/Santiago")

def ahora_chile():
    return datetime.datetime.now(CHILE_TZ)

def hora_chile():
    return ahora_chile().strftime("%H:%M")

FEE_USDT_CLP = 0.002
FEE_USDT_BS = 0.0025
FEE_WU = 0.025
FEE_CLP_BS = 0.055
FEE_BS_CLP = 0.055
FEE_CLP_COP = 0.075
FEE_COP_BS = 0.055
MARGEN_BS = 30
SPREAD_CLP = 50

SPREAD_SILENCIO = 10
SPREAD_MODERADO = 10
SPREAD_BUENO = 15
SPREAD_PREMIUM = 20
VARIACION_ALERTA = 0.02

western_rate = None
last_update_id = None
p2p_ultimo_spread_alerta = 0

tasa_dia_compra = None
tasa_dia_venta = None
tasa_dia_hora = None
historial_tasas = []
ultimo_cierre = None

def get_binance_fiat(fiat):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    def fetch(side):
        payload = {"asset":"USDT","fiat":fiat,"merchantCheck":False,"page":1,"publisherType":None,"rows":10,"tradeType":side,"payTypes":[]}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            ads = r.json()["data"][:3]
            prices = [float(ad["adv"]["price"]) for ad in ads]
            return round(sum(prices)/len(prices), 2) if prices else None
        except:
            return None
    return fetch("SELL"), fetch("BUY")

def get_binance_banco(banco):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    pay_venta = [banco, "PagoMovil"]
    def fetch_venta():
        payload = {"asset":"USDT","fiat":"VES","merchantCheck":False,"page":1,"publisherType":None,"rows":10,"tradeType":"BUY","payTypes":pay_venta,"transAmount":"1000"}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            ads = r.json()["data"][:3]
            prices = [float(ad["adv"]["price"]) for ad in ads]
            return round(sum(prices)/len(prices), 2) if prices else None
        except:
            return None
    def fetch_compra():
        payload = {"asset":"USDT","fiat":"VES","merchantCheck":False,"page":1,"publisherType":None,"rows":10,"tradeType":"SELL","payTypes":[banco],"transAmount":"1000"}
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
        return "Mercantil", mer_compra, mer_venta, mer_spread, "Banesco", ban_compra, ban_venta, ban_spread
    else:
        return "Banesco", ban_compra, ban_venta, ban_spread, "Mercantil", mer_compra, mer_venta, mer_spread

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
    if spread >= SPREAD_PREMIUM:
        return "🚀"
    elif spread >= SPREAD_BUENO:
        return "🟢"
    elif spread >= SPREAD_MODERADO:
        return "🟡"
    else:
        return "🔴"

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)

def fijar_tasa_dia(compra, venta):
    global tasa_dia_compra, tasa_dia_venta, tasa_dia_hora
    tasa_dia_compra = compra
    tasa_dia_venta = venta
    tasa_dia_hora = hora_chile()

def verificar_variacion(compra_actual, venta_actual):
    if not tasa_dia_venta or not venta_actual:
        return
    variacion = abs(venta_actual - tasa_dia_venta) / tasa_dia_venta
    if variacion >= VARIACION_ALERTA:
        signo = "📈" if venta_actual > tasa_dia_venta else "📉"
        msg  = f"⚠️ *ALERTA DE VARIACIÓN*\n\n"
        msg += f"La tasa se alejó `{variacion*100:.1f}%` de la referencia del día\n\n"
        msg += f"Tasa del día:\n"
        msg += f"  Compra: `{fmt(tasa_dia_compra)} Bs`\n"
        msg += f"  Venta:  `{fmt(tasa_dia_venta)} Bs`\n\n"
        msg += f"Tasa actual:\n"
        msg += f"  Compra: `{fmt(compra_actual)} Bs`\n"
        msg += f"  Venta:  `{fmt(venta_actual)} Bs` {signo}\n\n"
        msg += f"_Usa /actualizar\\_tasa para actualizar la referencia_"
        enviar_telegram(msg)

def registrar_historial(compra, venta, spread):
    historial_tasas.append({
        "hora": hora_chile(),
        "compra": compra,
        "venta": venta,
        "spread": spread
    })

def enviar_cierre_dia():
    global historial_tasas, ultimo_cierre
    if not historial_tasas:
        return
    hoy = ahora_chile()
    dias = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    fecha_str = f"{dias[hoy.weekday()]}, {hoy.day} de {meses[hoy.month-1]} {hoy.year}"
    compras = [t["compra"] for t in historial_tasas if t["compra"]]
    ventas = [t["venta"] for t in historial_tasas if t["venta"]]
    spreads = [t["spread"] for t in historial_tasas if t["spread"]]
    prom_compra = round(sum(compras)/len(compras), 2) if compras else 0
    prom_venta = round(sum(ventas)/len(ventas), 2) if ventas else 0
    prom_spread = round(sum(spreads)/len(spreads), 2) if spreads else 0
    max_spread = max(spreads) if spreads else 0
    min_spread = min(spreads) if spreads else 0
    mejor_momento = max(historial_tasas, key=lambda x: x["spread"]) if historial_tasas else None
    peor_momento = min(historial_tasas, key=lambda x: x["spread"]) if historial_tasas else None
    variacion_dia = ((historial_tasas[-1]["venta"] - historial_tasas[0]["venta"]) / historial_tasas[0]["venta"] * 100) if len(historial_tasas) > 1 else 0
    msg  = f"🌙 *CIERRE DEL DÍA*\n"
    msg += f"_{fecha_str}_\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"📌 *TASA DEL DÍA*\n\n"
    msg += f"Apertura {historial_tasas[0]['hora']}\n"
    msg += f"  Compra: `{fmt(historial_tasas[0]['compra'])} Bs`\n"
    msg += f"  Venta:  `{fmt(historial_tasas[0]['venta'])} Bs`\n\n"
    msg += f"Cierre {historial_tasas[-1]['hora']}\n"
    msg += f"  Compra: `{fmt(historial_tasas[-1]['compra'])} Bs`\n"
    msg += f"  Venta:  `{fmt(historial_tasas[-1]['venta'])} Bs`\n\n"
    msg += f"Promedio del día\n"
    msg += f"  Compra: `{fmt(prom_compra)} Bs`\n"
    msg += f"  Venta:  `{fmt(prom_venta)} Bs`\n\n"
    signo = "📈" if variacion_dia >= 0 else "📉"
    msg += f"Variación: `{variacion_dia:+.2f}%` {signo}\n\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"📊 *SPREAD DEL DÍA*\n\n"
    msg += f"Promedio: `{fmt(prom_spread)} Bs`\n"
    msg += f"Máximo:   `{fmt(max_spread)} Bs` — {mejor_momento['hora'] if mejor_momento else '--'}\n"
    msg += f"Mínimo:   `{fmt(min_spread)} Bs` — {peor_momento['hora'] if peor_momento else '--'}\n\n"
    msg += f"Registros: `{len(historial_tasas)}`\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━"
    enviar_telegram(msg)
    historial_tasas.clear()
    ultimo_cierre = hoy.date()

def analizar_spread_p2p(mejor_banco, compra, venta, spread):
    global p2p_ultimo_spread_alerta
    if not compra or not venta:
        return
    if spread < SPREAD_SILENCIO:
        p2p_ultimo_spread_alerta = 0
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
    bs_recibidos = 100 * (1 - FEE_USDT_BS) * venta
    bs_pagados = 100 * compra
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
    msg += f"  Ganancia neta:   `{fmt(ganancia_bs)} Bs`\n"
    msg += f"  En USDT:         `~{fmt(ganancia_usdt, 4)} USDT`\n\n"
    msg += f"_Vende con {mejor_banco} + Pago Móvil_\n"
    msg += f"_Compra solo con {mejor_banco}_"
    enviar_telegram(msg)
    p2p_ultimo_spread_alerta = spread

def construir_mensaje(mejor_banco, m_compra, m_venta, m_spread, o_banco, o_compra, o_venta, o_spread, clp_compra, clp_venta, cop_compra, cop_venta, usd_clp, trm, bcv_usd, bcv_eur):
    hoy = ahora_chile()
    dias = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    fecha_str = f"{dias[hoy.weekday()]}, {hoy.day} de {meses[hoy.month-1]} — {hoy.strftime('%I:%M %p')}"
    msg  = f"📊 *RESUMEN DE TASAS*\n"
    msg += f"📅 {fecha_str}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    if tasa_dia_venta and m_venta:
        variacion = ((m_venta - tasa_dia_venta) / tasa_dia_venta) * 100
        signo = "📈" if variacion >= 0 else "📉"
        msg += f"📌 *TASA DEL DÍA*\n"
        msg += f"  Compra: `{fmt(tasa_dia_compra)} Bs` | Venta: `{fmt(tasa_dia_venta)} Bs`\n"
        msg += f"  Fijada: {tasa_dia_hora} | Variación: `{variacion:+.2f}%` {signo}\n\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"🌎 *TASAS OFICIALES*\n\n"
    if trm:
        msg += f"🇨🇴  *TRM*\n      `{fmt(trm)} COP`\n\n"
    if bcv_usd:
        msg += f"🏦  *USD/BCV*\n      `{fmt(bcv_usd)} Bs`\n\n"
    if bcv_eur:
        msg += f"🏦  *EUR/BCV*\n      `{fmt(bcv_eur)} Bs`\n\n"
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
    global western_rate, last_update_id, tasa_dia_compra, tasa_dia_venta, tasa_dia_hora
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
            elif text.lower() == "/actualizar_tasa":
                mejor_banco, m_compra, m_venta, m_spread, _, _, _, _ = get_mejor_banco()
                if m_compra and m_venta:
                    fijar_tasa_dia(m_compra, m_venta)
                    enviar_telegram(f"✅ *Tasa del día actualizada*\n  Compra: `{fmt(m_compra)} Bs`\n  Venta: `{fmt(m_venta)} Bs`\n  Hora: {tasa_dia_hora}")
                else:
                    enviar_telegram("⚠️ No se pudo obtener la tasa en este momento.")
            elif text.lower() == "/tasa_dia":
                if tasa_dia_venta:
                    mejor_banco, m_compra, m_venta, _, _, _, _, _ = get_mejor_banco()
                    variacion = ((m_venta - tasa_dia_venta) / tasa_dia_venta * 100) if m_venta else 0
                    msg  = f"📌 *TASA DEL DÍA*\n\n"
                    msg += f"Compra: `{fmt(tasa_dia_compra)} Bs`\n"
                    msg += f"Venta:  `{fmt(tasa_dia_venta)} Bs`\n"
                    msg += f"Fijada: {tasa_dia_hora}\n\n"
                    msg += f"Tasa actual: `{fmt(m_venta)} Bs`\n"
                    msg += f"Variación: `{variacion:+.2f}%`\n\n"
                    msg += f"_Usa /actualizar\\_tasa para cambiarla_"
                    enviar_telegram(msg)
                else:
                    enviar_telegram("⚠️ No hay tasa del día fijada. Se fija automáticamente a las 9:00 AM.")
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
                    msg += f"_Spread por debajo del mínimo ({SPREAD_SILENCIO} Bs)_"
                enviar_telegram(msg)
            elif text.lower() == "/ayuda":
                msg  = "📋 *Comandos disponibles*\n\n"
                msg += "*Tasas:*\n"
                msg += "`/tasas` — Ver resumen completo\n"
                msg += "`/spread` — Ver spread Banesco vs Mercantil\n"
                msg += "`/western TASA` — Actualizar Western Unión\n\n"
                msg += "*Tasa del día:*\n"
                msg += "`/tasa_dia` — Ver tasa de referencia del día\n"
                msg += "`/actualizar_tasa` — Actualizar al precio actual\n\n"
                msg += "`/ayuda` — Ver esta lista"
                enviar_telegram(msg)
    except Exception as e:
        print(f"Error check_commands: {e}")
    return pedir_tasas

def main():
    global ultimo_cierre
    ultimo_envio_tasas = 0
    ultimo_check_p2p = 0
    ultimo_check_variacion = 0
    tasa_dia_fijada_hoy = False

    print("🚀 Bot GSA Cambios iniciado — Hora Chile")

    while True:
        pedir_tasas = check_commands()
        ahora = time.time()
        hora_actual = ahora_chile()

        if hora_actual.hour == 0 and hora_actual.minute == 0:
            tasa_dia_fijada_hoy = False

        if hora_actual.hour == 9 and hora_actual.minute == 0 and not tasa_dia_fijada_hoy:
            mejor_banco, m_compra, m_venta, m_spread, _, _, _, _ = get_mejor_banco()
            if m_compra and m_venta:
                fijar_tasa_dia(m_compra, m_venta)
                tasa_dia_fijada_hoy = True
                enviar_telegram(
                    f"🌅 *Buenos días — Tasa del día fijada*\n\n"
                    f"🏦 Banco: *{mejor_banco}*\n"
                    f"  Compra: `{fmt(m_compra)} Bs`\n"
                    f"  Venta:  `{fmt(m_venta)} Bs`\n"
                    f"  Spread: `{fmt(m_spread)} Bs` {spread_emoji(m_spread)}\n\n"
                    f"_¡Buen día de operaciones!_ 💪"
                )

        if hora_actual.hour == 23 and hora_actual.minute == 59:
            if ultimo_cierre != hora_actual.date():
                enviar_cierre_dia()

        if (ahora - ultimo_check_p2p) >= 300:
            mejor_banco, m_compra, m_venta, m_spread, _, _, _, _ = get_mejor_banco()
            analizar_spread_p2p(mejor_banco, m_compra, m_venta, m_spread)
            if m_compra and m_venta:
                registrar_historial(m_compra, m_venta, m_spread)
            ultimo_check_p2p = ahora

        if (ahora - ultimo_check_variacion) >= 1800:
            mejor_banco, m_compra, m_venta, m_spread, _, _, _, _ = get_mejor_banco()
            verificar_variacion(m_compra, m_venta)
            ultimo_check_variacion = ahora

        if pedir_tasas or (ahora - ultimo_envio_tasas) >= 1800:
            mejor_banco, m_compra, m_venta, m_spread, o_banco, o_compra, o_venta, o_spread = get_mejor_banco()
            clp_compra, clp_venta = get_binance_fiat("CLP")
            cop_compra, cop_venta = get_binance_fiat("COP")
            usd_clp = get_dolar_observado()
            trm = get_trm()
            bcv_usd, bcv_eur = get_bcv()
            msg = construir_mensaje(mejor_banco, m_compra, m_venta, m_spread, o_banco, o_compra, o_venta, o_spread, clp_compra, clp_venta, cop_compra, cop_venta, usd_clp, trm, bcv_usd, bcv_eur)
            enviar_telegram(msg)
            ultimo_envio_tasas = ahora
            print(f"Enviado — {hora_actual.strftime('%H:%M:%S')} Chile")

        time.sleep(10)

if __name__ == "__main__":
    main()
