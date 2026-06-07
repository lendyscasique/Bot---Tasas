# GSA CAMBIOS BOT v6.0 — INTELIGENCIA DE MERCADO
"""
GSA CAMBIOS — BOT COMPLETO v6.0
Nuevas funciones:
- Alertas con precios reales top 2 (no promedios)
- Tasas sincronizadas al reloj (en punto y media)
- Historial de precios cada 5 min
- Análisis de patrones y proyecciones
- Gestor de capital inteligente
- Reportes diario y semanal automáticos
- Comandos: /mercado /patron /simular /umbral /clientes /resumen_corresponsal
"""

import os
import csv
import time
import sqlite3
import datetime
import requests
import threading
import json
from collections import defaultdict

# ══════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH            = os.getenv("GSA_DB_PATH", "gsa_cambios.db")
CSV_EXPORT_PATH    = os.getenv("GSA_CSV_PATH", "csv_export")

# Zona horaria UTC-4 (Chile invierno = Venezuela)
UTC_OFFSET = -4

# ══════════════════════════════════════════════════════════════════════
# SUPABASE
# ══════════════════════════════════════════════════════════════════════
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)
print(f"🔗 Supabase: {'ACTIVADO' if USE_SUPABASE else 'DESACTIVADO'}")

def supa_insert(tabla, datos):
    if not USE_SUPABASE: return None
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{tabla}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json=datos, timeout=10)
        if r.status_code not in (200, 201):
            print(f"Supabase insert warn ({tabla}): {r.status_code} {r.text[:100]}")
        return r
    except Exception as e:
        print(f"Supabase insert error ({tabla}): {e}"); return None

def supa_select(tabla, query=""):
    if not USE_SUPABASE: return []
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabla}?{query}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print(f"Supabase select error ({tabla}): {e}"); return []

def supa_update(tabla, campo, valor, datos):
    if not USE_SUPABASE: return None
    try:
        r = requests.patch(f"{SUPABASE_URL}/rest/v1/{tabla}?{campo}=eq.{valor}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            json=datos, timeout=10)
        return r
    except Exception as e:
        print(f"Supabase update error ({tabla}): {e}"); return None

# ══════════════════════════════════════════════════════════════════════
# FEES Y CONFIGURACIÓN DE NEGOCIO
# ══════════════════════════════════════════════════════════════════════
FEE_USDT_BS  = 0.0025
FEE_USDT_CLP = 0.002
FEE_WU       = 0.025
FEE_CLP_BS   = 0.055
FEE_BS_CLP   = 0.055
FEE_CLP_COP  = 0.075
FEE_COP_CLP  = 0.075
FEE_COP_BS   = 0.055
FEE_BS_COP   = 0.055
MARGEN_BS    = 30
SPREAD_CLP   = 50

# Umbrales de alertas de mercado
SPREAD_MIN_ALERTA   = 10    # Bs mínimo para alertar
SPREAD_CAMBIO_BS    = 2     # Bs de variación para nueva alerta
CAMBIO_MIN_CLP      = 5     # CLP de variación para nueva alerta
SPREAD_SILENCIO     = 7
SPREAD_MODERADO     = 10
SPREAD_BUENO        = 15
SPREAD_PREMIUM      = 20

# Intervalos
INTERVALO_MERCADO_SEG   = 300   # 5 min
INTERVALO_LIQUIDEZ_SEG  = 900   # 15 min
INTERVALO_CSV_SEG       = 3600  # 1 hora

PAUSA_SESION_MIN = 45

TIPOS_OP = [
    "CLP→BS","BS→CLP","CLP→COP","COP→CLP","COP→BS","BS→COP",
    "CLP→USDT","USDT→CLP","BS→USDT","USDT→BS","USD→CLP","CLP→USD",
    "USD→BS","BS→USD","GIRO INT","USDC→USDT","USDT→USDC","USDT→USDT",
]
CORRESPONSALES = [
    "Bancolombia C1","Bancolombia C2",
    "Nequi C1","Nequi C2","Nequi C3","Efectivo Orlando",
]
NOMBRES_CUENTAS = {
    "BS_BANESCO":"Banesco","BS_MERCANTIL":"Mercantil",
    "CLP_COPEC_PAY":"Copec Pay","CLP_BANCOESTADO":"BancoEstado",
    "COP_EFECTIVO_ORLANDO":"Efectivo Orlando",
    "COP_BANCOLOMBIA_C1":"Bancolombia C1","COP_BANCOLOMBIA_C2":"Bancolombia C2",
    "COP_NEQUI_C1":"Nequi C1","COP_NEQUI_C2":"Nequi C2","COP_NEQUI_C3":"Nequi C3",
    "USD_EFECTIVO":"USD Efectivo","USDT_BINANCE":"Binance USDT","USDC_AIRTM":"Airtm USDC",
}
DIAS_SEMANA = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

# ══════════════════════════════════════════════════════════════════════
# UTILIDADES DE TIEMPO
# ══════════════════════════════════════════════════════════════════════
def now_local():
    """Hora actual en UTC-4."""
    return datetime.datetime.utcnow() + datetime.timedelta(hours=UTC_OFFSET)

def today_local():
    return now_local().date()

def hora_local():
    return now_local().strftime("%H:%M")

def dia_semana_local():
    return DIAS_SEMANA[now_local().weekday()]

# ══════════════════════════════════════════════════════════════════════
# BASE DE DATOS
# ══════════════════════════════════════════════════════════════════════
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn(); c = conn.cursor()
    # Tablas existentes
    c.execute("""CREATE TABLE IF NOT EXISTS tasas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
        bcv_usd REAL, bcv_eur REAL,
        ban_bs_compra REAL, ban_bs_venta REAL, ban_bs_spread REAL,
        mer_bs_compra REAL, mer_bs_venta REAL, mer_bs_spread REAL,
        clp_compra REAL, clp_venta REAL, cop_compra REAL, cop_venta REAL,
        trm REAL, dolar_obs REAL, western REAL,
        limite_clp_bs REAL, limite_clp_cop REAL, limite_bs_cop REAL,
        tasa_gsa_clp_bs REAL, tasa_gsa_bs_clp REAL,
        tasa_gsa_clp_cop REAL, tasa_gsa_cop_clp REAL,
        tasa_gsa_cop_bs REAL, tasa_gsa_bs_cop REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS operaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha DATE, hora TIME, cliente TEXT, referente TEXT, tipo_op TEXT,
        origen_fondos TEXT, mon_entrada TEXT, monto_entrada REAL,
        mon_salida TEXT, monto_salida REAL, tasa_cliente REAL, tasa_referencia REAL,
        usdt_equiv REAL, diferencial REAL, metodo TEXT, corresponsal TEXT,
        traslado_bs REAL DEFAULT 0, encomienda_cop REAL DEFAULT 0, repartidor TEXT,
        financiador TEXT, estado TEXT DEFAULT 'Completada', observaciones TEXT,
        cxc_pendiente REAL DEFAULT 0, cxp_pendiente REAL DEFAULT 0,
        snap_pat_bs REAL, snap_dol_obs REAL, snap_trm REAL,
        usuario_telegram TEXT, fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS saldos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cuenta TEXT UNIQUE,
        moneda TEXT, saldo REAL DEFAULT 0,
        ultima_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE,
        telefono TEXT, pais TEXT DEFAULT 'Venezuela',
        fecha_registro DATE DEFAULT CURRENT_DATE, ultima_operacion DATE,
        operaciones_total INTEGER DEFAULT 0, volumen_usdt REAL DEFAULT 0,
        ganancia_generada REAL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha DATE DEFAULT CURRENT_DATE,
        categoria TEXT, descripcion TEXT, monto REAL, moneda TEXT,
        usdt_equiv REAL, comprobante TEXT, usuario_telegram TEXT,
        fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tesoreria (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha DATE DEFAULT CURRENT_DATE,
        tipo TEXT, persona TEXT, direccion TEXT, monto REAL, moneda TEXT,
        usdt_equiv REAL, estado TEXT DEFAULT 'Completado', usuario_telegram TEXT,
        fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS cuentas_pendientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT,
        fecha DATE DEFAULT CURRENT_DATE, contraparte TEXT, concepto TEXT,
        monto REAL, moneda TEXT, usdt_equiv REAL, vencimiento DATE,
        prioridad TEXT DEFAULT '🟡 Esta semana', estado TEXT DEFAULT 'Pendiente',
        op_origen_id INTEGER, fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS auditoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
        usuario TEXT, accion TEXT, modulo TEXT, registro_id INTEGER,
        valor_anterior TEXT, valor_nuevo TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS saldos_iniciales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cuenta TEXT UNIQUE, saldo REAL DEFAULT 0,
        fecha DATE DEFAULT CURRENT_DATE)""")
    # TABLA NUEVA: precios_historicos
    c.execute("""CREATE TABLE IF NOT EXISTS precios_historicos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha DATE, hora TIME, dia_semana TEXT,
        bs_venta_1 REAL, bs_venta_2 REAL,
        bs_compra_1 REAL, bs_compra_2 REAL,
        bs_spread_real REAL,
        clp_compra_1 REAL, clp_compra_2 REAL,
        cop_compra_1 REAL, cop_compra_2 REAL,
        usuario_venta_1 TEXT, usuario_venta_2 TEXT,
        usuario_compra_1 TEXT, usuario_compra_2 TEXT,
        disp_venta_1 REAL, disp_venta_2 REAL,
        disp_compra_1 REAL, disp_compra_2 REAL,
        fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    # TABLA NUEVA: umbrales_liquidez
    c.execute("""CREATE TABLE IF NOT EXISTS umbrales_liquidez (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cuenta TEXT UNIQUE, umbral_minimo REAL, moneda TEXT,
        activo INTEGER DEFAULT 1)""")
    # TABLA NUEVA: config
    c.execute("""CREATE TABLE IF NOT EXISTS config (
        clave TEXT PRIMARY KEY, valor TEXT,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()
    print("✅ Base de datos v6.0 lista")

def init_saldos():
    cuentas = {
        "BS_BANESCO":"BS","BS_MERCANTIL":"BS",
        "CLP_COPEC_PAY":"CLP","CLP_BANCOESTADO":"CLP",
        "COP_EFECTIVO_ORLANDO":"COP","COP_BANCOLOMBIA_C1":"COP",
        "COP_BANCOLOMBIA_C2":"COP","COP_NEQUI_C1":"COP",
        "COP_NEQUI_C2":"COP","COP_NEQUI_C3":"COP",
        "USD_EFECTIVO":"USD","USDT_BINANCE":"USDT","USDC_AIRTM":"USDC",
    }
    conn = get_conn(); c = conn.cursor()
    for cuenta, moneda in cuentas.items():
        c.execute("INSERT OR IGNORE INTO saldos (cuenta,moneda,saldo) VALUES (?,?,0)", (cuenta, moneda))
    conn.commit(); conn.close()

def get_config(clave, default=""):
    conn = get_conn()
    row = conn.execute("SELECT valor FROM config WHERE clave=?", (clave,)).fetchone()
    conn.close()
    return row['valor'] if row else default

def set_config(clave, valor):
    conn = get_conn()
    conn.execute("INSERT INTO config (clave,valor,actualizado) VALUES (?,?,CURRENT_TIMESTAMP) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor, actualizado=CURRENT_TIMESTAMP",
                 (clave, str(valor)))
    conn.commit(); conn.close()

# ══════════════════════════════════════════════════════════════════════
# APIS BINANCE — PRECIOS REALES TOP 2
# ══════════════════════════════════════════════════════════════════════
def get_top_anuncios_bs():
    """Retorna top 2 compra y top 2 venta reales para BS (VES)."""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}

    def fetch_ads(side, pay_types=None):
        try:
            r = requests.post(url, headers=headers, json={
                "asset": "USDT", "fiat": "VES", "merchantCheck": False,
                "page": 1, "publisherType": None, "rows": 5,
                "tradeType": side, "payTypes": pay_types or []}, timeout=10)
            ads = r.json().get("data", [])
            result = []
            for a in ads[:2]:
                adv = a.get("adv", {})
                adv2 = a.get("advertiser", {})
                result.append({
                    "precio": float(adv.get("price", 0)),
                    "usuario": adv2.get("nickName", "—"),
                    "disponible": float(adv.get("surplusAmount", 0)),
                })
            return result
        except: return []

    compras = fetch_ads("SELL", ["Banesco", "Mercantil", "PagoMovil"])
    ventas  = fetch_ads("BUY",  ["Banesco", "Mercantil", "PagoMovil"])
    return compras, ventas

def get_top_anuncios_clp():
    """Retorna top 2 compradores de USDT en CLP (para ti como Maker vendedor)."""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json={
            "asset": "USDT", "fiat": "CLP", "merchantCheck": False,
            "page": 1, "publisherType": None, "rows": 5,
            "tradeType": "BUY", "payTypes": []}, timeout=10)
        ads = r.json().get("data", [])
        result = []
        for a in ads[:2]:
            adv = a.get("adv", {})
            adv2 = a.get("advertiser", {})
            result.append({
                "precio": float(adv.get("price", 0)),
                "usuario": adv2.get("nickName", "—"),
                "disponible": float(adv.get("surplusAmount", 0)),
            })
        return result
    except: return []

def get_top_anuncios_cop():
    """Top 2 compradores COP."""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json={
            "asset": "USDT", "fiat": "COP", "merchantCheck": False,
            "page": 1, "publisherType": None, "rows": 5,
            "tradeType": "BUY", "payTypes": []}, timeout=10)
        ads = r.json().get("data", [])
        result = []
        for a in ads[:2]:
            adv = a.get("adv", {})
            adv2 = a.get("advertiser", {})
            result.append({
                "precio": float(adv.get("price", 0)),
                "usuario": adv2.get("nickName", "—"),
                "disponible": float(adv.get("surplusAmount", 0)),
            })
        return result
    except: return []

def get_binance_banco_promedio(banco):
    """Promedio de 3 anuncios — solo para calcular tasas GSA y límites."""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    def fetch(side, pay):
        try:
            r = requests.post(url, headers=headers, json={
                "asset":"USDT","fiat":"VES","merchantCheck":False,"page":1,
                "publisherType":None,"rows":10,"tradeType":side,
                "payTypes":pay,"transAmount":"1000"}, timeout=10)
            ads = r.json()["data"][:3]
            prices = [float(a["adv"]["price"]) for a in ads]
            return round(sum(prices)/len(prices),2) if prices else None
        except: return None
    compra = fetch("SELL",[banco])
    venta  = fetch("BUY",[banco,"PagoMovil"])
    spread = round(venta-compra,2) if venta and compra else 0
    return compra, venta, spread

def get_binance_fiat_promedio(fiat):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    def fetch(side):
        try:
            r = requests.post(url,headers=headers,json={
                "asset":"USDT","fiat":fiat,"merchantCheck":False,"page":1,
                "publisherType":None,"rows":10,"tradeType":side,"payTypes":[]},timeout=10)
            ads = r.json()["data"][:3]
            prices = [float(a["adv"]["price"]) for a in ads]
            return round(sum(prices)/len(prices),2) if prices else None
        except: return None
    return fetch("SELL"), fetch("BUY")

def get_dolar_observado():
    try:
        data = requests.get("https://mindicador.cl/api/dolar",timeout=10).json()
        return float(data["serie"][0]["valor"])
    except: return None

def get_trm():
    try:
        ayer = (datetime.date.today()-datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        url = f"https://www.datos.gov.co/resource/32sa-8pi3.json?$where=vigenciadesde>='{ayer}T00:00:00.000'&$order=vigenciadesde DESC&$limit=1"
        data = requests.get(url,timeout=10).json()
        return float(data[0]["valor"]) if data else None
    except: return None

def get_bcv():
    try:
        data = requests.get("https://ve.dolarapi.com/v1/dolares/oficiales",timeout=10).json()
        usd = eur = None
        for item in data:
            m = item.get("moneda","").lower()
            if m=="usd": usd=float(item.get("promedio",0))
            elif m=="eur": eur=float(item.get("promedio",0))
        return usd, eur
    except: return None, None

# ══════════════════════════════════════════════════════════════════════
# GUARDAR HISTORIAL DE PRECIOS
# ══════════════════════════════════════════════════════════════════════
def guardar_precio_historico(compras_bs, ventas_bs, clp_ads, cop_ads):
    """Guarda snapshot de precios en precios_historicos."""
    ahora = now_local()
    fecha = str(ahora.date())
    hora  = ahora.strftime("%H:%M")
    dia   = DIAS_SEMANA[ahora.weekday()]

    bs_c1 = compras_bs[0]['precio'] if len(compras_bs) > 0 else None
    bs_c2 = compras_bs[1]['precio'] if len(compras_bs) > 1 else None
    bs_v1 = ventas_bs[0]['precio']  if len(ventas_bs)  > 0 else None
    bs_v2 = ventas_bs[1]['precio']  if len(ventas_bs)  > 1 else None
    spread = round(bs_v1 - bs_c1, 2) if bs_v1 and bs_c1 else None

    datos = {
        'fecha': fecha, 'hora': hora, 'dia_semana': dia,
        'bs_venta_1': bs_v1, 'bs_venta_2': bs_v2,
        'bs_compra_1': bs_c1, 'bs_compra_2': bs_c2,
        'bs_spread_real': spread,
        'clp_compra_1': clp_ads[0]['precio'] if len(clp_ads) > 0 else None,
        'clp_compra_2': clp_ads[1]['precio'] if len(clp_ads) > 1 else None,
        'cop_compra_1': cop_ads[0]['precio'] if len(cop_ads) > 0 else None,
        'cop_compra_2': cop_ads[1]['precio'] if len(cop_ads) > 1 else None,
        'usuario_venta_1': ventas_bs[0]['usuario']  if len(ventas_bs)  > 0 else None,
        'usuario_venta_2': ventas_bs[1]['usuario']  if len(ventas_bs)  > 1 else None,
        'usuario_compra_1': compras_bs[0]['usuario'] if len(compras_bs) > 0 else None,
        'usuario_compra_2': compras_bs[1]['usuario'] if len(compras_bs) > 1 else None,
        'disp_venta_1': ventas_bs[0]['disponible']  if len(ventas_bs)  > 0 else None,
        'disp_venta_2': ventas_bs[1]['disponible']  if len(ventas_bs)  > 1 else None,
        'disp_compra_1': compras_bs[0]['disponible'] if len(compras_bs) > 0 else None,
        'disp_compra_2': compras_bs[1]['disponible'] if len(compras_bs) > 1 else None,
    }

    conn = get_conn()
    conn.execute("""INSERT INTO precios_historicos
        (fecha,hora,dia_semana,bs_venta_1,bs_venta_2,bs_compra_1,bs_compra_2,
         bs_spread_real,clp_compra_1,clp_compra_2,cop_compra_1,cop_compra_2,
         usuario_venta_1,usuario_venta_2,usuario_compra_1,usuario_compra_2,
         disp_venta_1,disp_venta_2,disp_compra_1,disp_compra_2)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datos['fecha'],datos['hora'],datos['dia_semana'],
         datos['bs_venta_1'],datos['bs_venta_2'],datos['bs_compra_1'],datos['bs_compra_2'],
         datos['bs_spread_real'],datos['clp_compra_1'],datos['clp_compra_2'],
         datos['cop_compra_1'],datos['cop_compra_2'],
         datos['usuario_venta_1'],datos['usuario_venta_2'],
         datos['usuario_compra_1'],datos['usuario_compra_2'],
         datos['disp_venta_1'],datos['disp_venta_2'],
         datos['disp_compra_1'],datos['disp_compra_2']))
    conn.commit(); conn.close()

    if USE_SUPABASE:
        supa_insert('precios_historicos', datos)

    return datos

# ══════════════════════════════════════════════════════════════════════
# ANÁLISIS DE PATRONES
# ══════════════════════════════════════════════════════════════════════
def analizar_patron_bs():
    """Analiza el historial para detectar patrones de precio BS."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT hora, dia_semana, bs_venta_1, bs_compra_1, bs_spread_real
        FROM precios_historicos
        WHERE bs_venta_1 IS NOT NULL AND bs_compra_1 IS NOT NULL
        ORDER BY fecha DESC, hora
    """).fetchall()
    conn.close()

    if len(rows) < 20:
        return None, "Datos insuficientes. El bot necesita al menos 1 día de historial."

    # Agrupar por hora
    por_hora = defaultdict(list)
    for r in rows:
        hora_bloque = r['hora'][:2] + ":00"
        por_hora[hora_bloque].append({
            'venta': r['bs_venta_1'],
            'compra': r['bs_compra_1'],
            'spread': r['bs_spread_real'] or 0
        })

    resumen = {}
    for hora, datos in sorted(por_hora.items()):
    	ventas = [d['venta'] for d in datos]
    	spreads = [d['spread'] for d in datos]
    	resumen[hora] = {
    		'venta_prom': round(sum(ventas)/len(ventas), 2),
    		'spread_prom': round(sum(spreads)/len(spreads), 2),
    		'venta_max': max(ventas),
    		'venta_min': min(ventas),
    	}

    # Mejor y peor hora
    mejor_hora = max(resumen.items(), key=lambda x: x[1]['spread_prom'])
    peor_hora  = min(resumen.items(), key=lambda x: x[1]['spread_prom'])

    return resumen, mejor_hora, peor_hora

def proyeccion_manana():
    """Proyecta precios para mañana basado en mismo día de la semana."""
    manana = now_local() + datetime.timedelta(days=1)
    dia_manana = DIAS_SEMANA[manana.weekday()]

    conn = get_conn()
    rows = conn.execute("""
        SELECT hora, bs_venta_1, bs_spread_real
        FROM precios_historicos
        WHERE dia_semana=? AND bs_venta_1 IS NOT NULL
        ORDER BY fecha DESC, hora
    """, (dia_manana,)).fetchall()
    conn.close()

    if len(rows) < 5:
        return None, dia_manana

    por_hora = defaultdict(list)
    for r in rows:
        hora_bloque = r['hora'][:2] + ":00"
        por_hora[hora_bloque].append({
            'venta': r['bs_venta_1'],
            'spread': r['bs_spread_real'] or 0
        })

    proyeccion = {}
    for hora, datos in sorted(por_hora.items()):
        ventas = [d['venta'] for d in datos]
        spreads = [d['spread'] for d in datos]
        proyeccion[hora] = {
            'venta_esperada': round(sum(ventas)/len(ventas), 2),
            'spread_esperado': round(sum(spreads)/len(spreads), 2),
            'min': min(ventas),
            'max': max(ventas),
        }

    return proyeccion, dia_manana

# ══════════════════════════════════════════════════════════════════════
# GESTOR DE CAPITAL INTELIGENTE
# ══════════════════════════════════════════════════════════════════════
def analizar_capital():
    """Analiza el capital disponible vs el histórico y sugiere acciones."""
    saldos = get_saldos()
    t = get_ultima_tasa()
    ahora = now_local()
    hora_actual = ahora.hour
    dia_actual = DIAS_SEMANA[ahora.weekday()]

    pat_bs  = ((t.get('ban_bs_compra',0) or 0) + (t.get('ban_bs_venta',0) or 0)) / 2 or 1
    dol_obs = t.get('dolar_obs',1) or 1
    trm     = t.get('trm',1) or 1

    # Saldos actuales
    bs_total  = (saldos.get('BS_BANESCO',{}).get('saldo',0) or 0) + (saldos.get('BS_MERCANTIL',{}).get('saldo',0) or 0)
    clp_total = saldos.get('CLP_COPEC_PAY',{}).get('saldo',0) or 0
    cop_total = (saldos.get('COP_EFECTIVO_ORLANDO',{}).get('saldo',0) or 0)
    usdt_total = saldos.get('USDT_BINANCE',{}).get('saldo',0) or 0

    # Convertir todo a USDT
    bs_usdt   = bs_total / pat_bs if pat_bs else 0
    clp_usdt  = clp_total / dol_obs if dol_obs else 0
    cop_usdt  = cop_total / trm if trm else 0
    patrimonio_usdt = bs_usdt + clp_usdt + cop_usdt + usdt_total

    alertas = []

    # Revisar umbrales configurados
    conn = get_conn()
    umbrales = conn.execute("SELECT * FROM umbrales_liquidez WHERE activo=1").fetchall()
    conn.close()

    for u in umbrales:
        saldo_cuenta = saldos.get(u['cuenta'],{}).get('saldo',0) or 0
        if saldo_cuenta < u['umbral_minimo']:
            nombre = NOMBRES_CUENTAS.get(u['cuenta'], u['cuenta'])
            alertas.append({
                'tipo': 'umbral',
                'cuenta': nombre,
                'saldo': saldo_cuenta,
                'umbral': u['umbral_minimo'],
                'moneda': u['moneda'],
            })

    # Análisis de desbalance
    if patrimonio_usdt > 10:
        bs_pct   = bs_usdt / patrimonio_usdt * 100
        clp_pct  = clp_usdt / patrimonio_usdt * 100
        usdt_pct = usdt_total / patrimonio_usdt * 100

        if clp_pct < 10 and hora_actual >= 8 and hora_actual <= 20:
            alertas.append({
                'tipo': 'desbalance',
                'mensaje': f'Solo {clp_pct:.0f}% del capital en CLP. Operaciones CLP limitadas.',
                'sugerencia': f'Considera convertir USDT→CLP o BS→CLP'
            })
        if bs_pct < 10 and hora_actual >= 8 and hora_actual <= 20:
            alertas.append({
                'tipo': 'desbalance',
                'mensaje': f'Solo {bs_pct:.0f}% del capital en BS. Arbitraje BS limitado.',
                'sugerencia': f'Considera inyectar BS o convertir USDT→BS'
            })

    # Actividad esperada basada en historial
    conn = get_conn()
    ops_historico = conn.execute("""
        SELECT COUNT(*) as cnt FROM operaciones
        WHERE strftime('%H', hora) = ? AND dia_semana_local = ?
        AND estado='Completada'
    """, (str(hora_actual).zfill(2), dia_actual)).fetchone()
    conn.close()

    return {
        'bs_total': bs_total,
        'clp_total': clp_total,
        'cop_total': cop_total,
        'usdt_total': usdt_total,
        'patrimonio_usdt': patrimonio_usdt,
        'alertas': alertas,
    }

def msg_capital():
    """Genera mensaje del análisis de capital."""
    c = analizar_capital()
    t = get_ultima_tasa()
    pat_bs = ((t.get('ban_bs_compra',0) or 0) + (t.get('ban_bs_venta',0) or 0)) / 2 or 1
    dol_obs = t.get('dolar_obs',1) or 1

    m = f"💼 *ANÁLISIS DE CAPITAL*\n📅 {now_local().strftime('%d/%m %I:%M %p')}\n━━━━━━━━━━━━━━━━━━━━\n\n"
    m += f"🇻🇪 BS disponible: `{c['bs_total']:,.0f} Bs` (~`{c['bs_total']/pat_bs:.2f} USDT`)\n"
    m += f"🇨🇱 CLP disponible: `{c['clp_total']:,.0f} CLP` (~`{c['clp_total']/dol_obs:.2f} USDT`)\n"
    m += f"💎 USDT disponible: `{c['usdt_total']:.4f} USDT`\n"
    m += f"🏛️ Patrimonio total: `{c['patrimonio_usdt']:.2f} USDT`\n\n"

    if c['alertas']:
        m += "⚠️ *ALERTAS DE CAPITAL:*\n\n"
        for a in c['alertas']:
            if a['tipo'] == 'umbral':
                m += f"🔴 *{a['cuenta']}*: `{a['saldo']:,.2f}` (mín: `{a['umbral']:,.2f} {a['moneda']}`)\n"
            elif a['tipo'] == 'desbalance':
                m += f"🟡 {a['mensaje']}\n   _{a['sugerencia']}_\n"
        m += "\n"
    else:
        m += "✅ Capital balanceado\n\n"

    return m

# ══════════════════════════════════════════════════════════════════════
# SIMULADOR DE OPERACIONES
# ══════════════════════════════════════════════════════════════════════
def simular_operacion(moneda_origen, monto):
    """Simula cuánto ganas operando X monto ahora mismo."""
    t = get_ultima_tasa()
    compras_bs, ventas_bs = get_top_anuncios_bs()
    clp_ads = get_top_anuncios_clp()

    pat_bs = ((t.get('ban_bs_compra',0) or 0) + (t.get('ban_bs_venta',0) or 0)) / 2 or 1
    dol_obs = t.get('dolar_obs',1) or 1

    m = f"🧮 *SIMULADOR GSA*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    m += f"Capital: `{monto:,.2f} {moneda_origen}`\n\n"

    if moneda_origen == 'CLP':
        precio_compra_clp = clp_ads[0]['precio'] if clp_ads else dol_obs
        usdt = monto / precio_compra_clp
        m += f"🔵 *CLP → USDT (Binance Maker)*\n"
        m += f"   Precio compra: `{precio_compra_clp:,.2f} CLP`\n"
        m += f"   Recibes: `{usdt:.4f} USDT`\n\n"

        if ventas_bs:
            precio_venta_bs = ventas_bs[0]['precio']
            bs_recibidos = usdt * precio_venta_bs * (1 - FEE_USDT_BS)
            clp_recuperado = bs_recibidos / pat_bs * dol_obs
            ganancia_clp = clp_recuperado - monto
            ganancia_usdt = ganancia_clp / dol_obs
            m += f"🔵 *USDT → BS → CLP (triangular)*\n"
            m += f"   Precio venta BS: `{precio_venta_bs:,.2f} Bs`\n"
            m += f"   BS recibidos: `{bs_recibidos:,.0f} Bs`\n"
            m += f"   CLP recuperados: `{clp_recuperado:,.0f} CLP`\n"
            rentable = "✅ RENTABLE" if ganancia_clp > 0 else "❌ NO RENTABLE"
            m += f"\n💰 *Ganancia: `{ganancia_clp:,.0f} CLP` (~`{ganancia_usdt:.2f} USDT`)* {rentable}\n"

    elif moneda_origen == 'BS':
        precio_compra_bs = compras_bs[0]['precio'] if compras_bs else pat_bs
        usdt = monto / precio_compra_bs * (1 - FEE_USDT_BS)
        m += f"🔵 *BS → USDT (Binance Maker)*\n"
        m += f"   Precio compra: `{precio_compra_bs:,.2f} Bs`\n"
        m += f"   Recibes: `{usdt:.4f} USDT`\n\n"

        if ventas_bs:
            precio_venta_bs = ventas_bs[0]['precio']
            bs_recuperados = usdt * precio_venta_bs
            ganancia_bs = bs_recuperados - monto
            ganancia_usdt = ganancia_bs / precio_compra_bs
            m += f"🔵 *USDT → BS (venta)*\n"
            m += f"   Precio venta: `{precio_venta_bs:,.2f} Bs`\n"
            m += f"   BS recuperados: `{bs_recuperados:,.0f} Bs`\n"
            rentable = "✅ RENTABLE" if ganancia_bs > 0 else "❌ NO RENTABLE"
            m += f"\n💰 *Ganancia: `{ganancia_bs:,.0f} Bs` (~`{ganancia_usdt:.4f} USDT`)* {rentable}\n"

    elif moneda_origen == 'USDT':
        m += f"*Con `{monto:.4f} USDT` puedes:*\n\n"
        if ventas_bs:
            bs = monto * ventas_bs[0]['precio'] * (1-FEE_USDT_BS)
            m += f"🇻🇪 Vender en BS: `{bs:,.0f} Bs` (@{ventas_bs[0]['precio']} Bs)\n"
        if clp_ads:
            clp = monto * clp_ads[0]['precio']
            m += f"🇨🇱 Vender en CLP: `{clp:,.0f} CLP` (@{clp_ads[0]['precio']} CLP)\n"

    m += f"\n_Precios en tiempo real — {now_local().strftime('%H:%M')}_"
    return m

# ══════════════════════════════════════════════════════════════════════
# MENSAJES DE MERCADO
# ══════════════════════════════════════════════════════════════════════
def msg_mercado():
    """Mensaje con top 2 precios reales BS y CLP."""
    compras_bs, ventas_bs = get_top_anuncios_bs()
    clp_ads = get_top_anuncios_clp()
    ahora = now_local().strftime("%d/%m %I:%M %p")

    m = f"📡 *MERCADO EN VIVO*\n📅 {ahora}\n━━━━━━━━━━━━━━━━━━━━\n\n"

    m += "🇻🇪 *BINANCE BS*\n\n"
    if compras_bs:
        m += "📥 *Compra (pagas Bs, recibes USDT):*\n"
        for i, a in enumerate(compras_bs, 1):
            m += f"  {i}️⃣ `{a['usuario']:15s}` `{a['precio']:,.2f} Bs` | `{a['disponible']:.2f} USDT` disp.\n"
    if ventas_bs:
        m += "\n📤 *Venta (vendes USDT, recibes Bs):*\n"
        for i, a in enumerate(ventas_bs, 1):
            m += f"  {i}️⃣ `{a['usuario']:15s}` `{a['precio']:,.2f} Bs` | `{a['disponible']:.2f} USDT` disp.\n"
    if compras_bs and ventas_bs:
        spread = ventas_bs[0]['precio'] - compras_bs[0]['precio']
        emoji = "🚀" if spread >= SPREAD_PREMIUM else "🟢" if spread >= SPREAD_BUENO else "🟡" if spread >= SPREAD_MODERADO else "🔴"
        m += f"\n  Spread real: `{spread:.2f} Bs` {emoji}\n"
        m += f"  💡 Tu precio de venta sugerido: `{ventas_bs[0]['precio']+1:.2f} Bs`\n"

    m += "\n━━━━━━━━━━━━━━━━━━━━\n"
    m += "🇨🇱 *BINANCE CLP (compradores de USDT):*\n"
    if clp_ads:
        for i, a in enumerate(clp_ads, 1):
            m += f"  {i}️⃣ `{a['usuario']:15s}` `{a['precio']:,.2f} CLP` | `{a['disponible']:.2f} USDT` disp.\n"
        m += f"\n  💡 Para ser competitivo: publica a `{clp_ads[0]['precio']+1:.2f} CLP`\n"

    return m

def msg_alerta_bs(compras_bs, ventas_bs, spread):
    """Mensaje de alerta cuando el spread BS supera el umbral."""
    if spread >= SPREAD_PREMIUM: emoji, nivel = "🚀", "PREMIUM"
    elif spread >= SPREAD_BUENO: emoji, nivel = "🟢", "BUENO"
    else: emoji, nivel = "🟡", "MODERADO"

    m = f"{emoji} *SEÑAL BS — {nivel}* | Spread: `{spread:.2f} Bs`\n\n"
    if compras_bs:
        m += "📥 *Compra:*\n"
        for i, a in enumerate(compras_bs, 1):
            m += f"  {i}️⃣ `{a['usuario']:12s}` `{a['precio']:,.2f} Bs` | `{a['disponible']:.1f} USDT`\n"
    if ventas_bs:
        m += "\n📤 *Venta:*\n"
        for i, a in enumerate(ventas_bs, 1):
            m += f"  {i}️⃣ `{a['usuario']:12s}` `{a['precio']:,.2f} Bs` | `{a['disponible']:.1f} USDT`\n"
        m += f"\n💡 Publica venta a: `{ventas_bs[0]['precio']+1:.2f} Bs`"
    return m

def msg_alerta_clp(clp_ads):
    """Mensaje de alerta cuando el precio CLP cambia."""
    m = f"🇨🇱 *PRECIO CLP ACTUALIZADO*\n\n"
    m += "*Compradores de USDT disponibles:*\n"
    for i, a in enumerate(clp_ads, 1):
        m += f"  {i}️⃣ `{a['usuario']:12s}` `{a['precio']:,.2f} CLP` | `{a['disponible']:.1f} USDT`\n"
    if clp_ads:
        m += f"\n💡 Para ser competitivo: publica a `{clp_ads[0]['precio']+1:.2f} CLP`"
    return m

def msg_alerta_triangular(monto_clp, clp_ads, ventas_bs, t):
    """Alerta cuando hay oportunidad de arbitraje triangular."""
    if not clp_ads or not ventas_bs: return None
    precio_clp = clp_ads[0]['precio']
    precio_venta_bs = ventas_bs[0]['precio']
    pat_bs = ((t.get('ban_bs_compra',0) or 0) + (t.get('ban_bs_venta',0) or 0)) / 2 or 1
    dol_obs = t.get('dolar_obs',1) or 1

    usdt = monto_clp / precio_clp
    bs_recibidos = usdt * precio_venta_bs * (1-FEE_USDT_BS)
    clp_recuperado = bs_recibidos / pat_bs * dol_obs
    ganancia = clp_recuperado - monto_clp
    pct = (ganancia / monto_clp) * 100

    if ganancia <= 0 or pct < 1: return None

    m = f"🔺 *ARBITRAJE TRIANGULAR DETECTADO*\n\n"
    m += f"`{monto_clp:,.0f} CLP → {usdt:.2f} USDT → {bs_recibidos:,.0f} Bs → {clp_recuperado:,.0f} CLP`\n\n"
    m += f"💰 Ganancia estimada: `{ganancia:,.0f} CLP` (`{pct:.1f}%`)\n"
    m += f"_Usa /simular CLP {monto_clp:.0f} para confirmar_"
    return m

# ══════════════════════════════════════════════════════════════════════
# REPORTES DIARIO Y SEMANAL
# ══════════════════════════════════════════════════════════════════════
def generar_reporte_diario():
    """Genera el reporte de análisis del día."""
    hoy = str(today_local())
    conn = get_conn()
    rows = conn.execute("""
        SELECT hora, bs_venta_1, bs_compra_1, bs_spread_real
        FROM precios_historicos
        WHERE fecha=? AND bs_venta_1 IS NOT NULL
        ORDER BY hora
    """, (hoy,)).fetchall()
    conn.close()

    if not rows:
        return "📊 Sin datos de mercado para analizar hoy."

    ventas = [(r['hora'], r['bs_venta_1']) for r in rows]
    spreads = [(r['hora'], r['bs_spread_real'] or 0) for r in rows]

    max_venta = max(ventas, key=lambda x: x[1])
    min_venta = min(ventas, key=lambda x: x[1])
    max_spread = max(spreads, key=lambda x: x[1])
    min_spread = min(spreads, key=lambda x: x[1])

    prom_venta = sum(v for _,v in ventas) / len(ventas)
    prom_spread = sum(s for _,s in spreads) / len(spreads)

    # Mejor ventana (hora con mayor spread promedio)
    por_hora = defaultdict(list)
    for r in rows:
        por_hora[r['hora'][:2]].append(r['bs_spread_real'] or 0)
    mejor_ventana = max(por_hora.items(), key=lambda x: sum(x[1])/len(x[1]))

    res_hoy = get_resultados_hoy()

    m = f"📊 *ANÁLISIS DIARIO — {now_local().strftime('%d/%m/%Y')}*\n"
    m += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    m += f"📈 *PRECIO BS HOY*\n"
    m += f"  Venta más alta: `{max_venta[1]:.2f} Bs` a las `{max_venta[0]}`\n"
    m += f"  Venta más baja: `{min_venta[1]:.2f} Bs` a las `{min_venta[0]}`\n"
    m += f"  Promedio: `{prom_venta:.2f} Bs`\n\n"
    m += f"📊 *SPREAD BS HOY*\n"
    m += f"  Máximo: `{max_spread[1]:.2f} Bs` a las `{max_spread[0]}`\n"
    m += f"  Mínimo: `{min_spread[1]:.2f} Bs` a las `{min_spread[0]}`\n"
    m += f"  Promedio: `{prom_spread:.2f} Bs`\n\n"
    m += f"🏆 *Mejor ventana:* `{mejor_ventana[0]}:00 — {int(mejor_ventana[0])+1:02d}:00`\n\n"
    m += f"💼 *OPERACIONES HOY*\n"
    m += f"  Ops: `{res_hoy['ops']}` | Vol: `{res_hoy['volumen']:.4f} USDT`\n"
    m += f"  Ganancia neta: `{res_hoy['ganancia_neta']:.4f} USDT`\n\n"
    m += f"_Mañana: usa /patron para proyección_"
    return m

def generar_reporte_semanal():
    """Genera el reporte semanal con proyección."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT dia_semana, hora, bs_venta_1, bs_spread_real
        FROM precios_historicos
        WHERE bs_venta_1 IS NOT NULL
        ORDER BY fecha DESC, hora
        LIMIT 2000
    """).fetchall()
    conn.close()

    if len(rows) < 50:
        return "📅 Datos insuficientes para reporte semanal. Se necesita al menos 1 semana de historial."

    por_dia = defaultdict(list)
    for r in rows:
        por_dia[r['dia_semana']].append({
            'venta': r['bs_venta_1'],
            'spread': r['bs_spread_real'] or 0,
            'hora': r['hora'][:2]
        })

    m = f"📅 *REPORTE SEMANAL BS*\n"
    m += f"━━━━━━━━━━━━━━━━━━━━\n\n"

    for dia in DIAS_SEMANA:
        if dia not in por_dia: continue
        datos = por_dia[dia]
        ventas = [d['venta'] for d in datos]
        spreads = [d['spread'] for d in datos]
        por_hora_dia = defaultdict(list)
        for d in datos: por_hora_dia[d['hora']].append(d['spread'])
        mejor_h = max(por_hora_dia.items(), key=lambda x: sum(x[1])/len(x[1])) if por_hora_dia else ("??", [0])
        m += f"*{dia}:* venta prom `{sum(ventas)/len(ventas):.2f} Bs` | spread prom `{sum(spreads)/len(spreads):.2f} Bs` | mejor hora `{mejor_h[0]}:00`\n"

    # Proyección
    proyeccion, dia_manana = proyeccion_manana()
    m += f"\n🔮 *PROYECCIÓN {dia_manana.upper()}*\n"
    if proyeccion:
        ventanas = [(h, d) for h, d in proyeccion.items() if d['spread_esperado'] >= SPREAD_MIN_ALERTA]
        if ventanas:
            m += "Ventanas con spread ≥ 10 Bs esperado:\n"
            for hora, d in sorted(ventanas, key=lambda x: x[1]['spread_esperado'], reverse=True)[:3]:
                m += f"  `{hora}` → spread ~`{d['spread_esperado']:.1f} Bs` | venta ~`{d['venta_esperada']:.2f} Bs`\n"
        else:
            m += "_Sin ventanas de alto spread proyectadas_\n"
    else:
        m += "_Sin suficiente historial para proyectar_\n"

    return m

# ══════════════════════════════════════════════════════════════════════
# RESUMEN DE CORRESPONSALES Y CLIENTES
# ══════════════════════════════════════════════════════════════════════
def msg_resumen_corresponsal(nombre):
    conn = get_conn()
    ops = conn.execute("""
        SELECT COUNT(*) as total, COALESCE(SUM(usdt_equiv),0) as vol
        FROM operaciones WHERE corresponsal LIKE ? AND estado='Completada'
    """, (f'%{nombre}%',)).fetchone()
    cxp = conn.execute("""
        SELECT COALESCE(SUM(monto),0) as total, COUNT(*) as cnt
        FROM cuentas_pendientes WHERE contraparte LIKE ? AND estado='Pendiente' AND tipo='CXP'
    """, (f'%{nombre}%',)).fetchone()
    conn.close()

    m = f"🏦 *CORRESPONSAL: {nombre.upper()}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    m += f"Operaciones: `{ops['total']}`\n"
    m += f"Volumen total: `{ops['vol']:.4f} USDT`\n"
    m += f"Comisión acumulada (2.5%): `{ops['vol']*0.025:.4f} USDT`\n\n"
    m += f"💰 *Pendiente por pagar:*\n"
    m += f"  `{cxp['total']:.4f} USDT` ({cxp['cnt']} registros)\n"
    return m

def msg_clientes_top():
    conn = get_conn()
    rows = conn.execute("""
        SELECT nombre, operaciones_total, volumen_usdt
        FROM clientes ORDER BY volumen_usdt DESC LIMIT 5
    """).fetchall()
    conn.close()
    if not rows: return "Sin clientes registrados aún."
    m = "🏆 *TOP CLIENTES*\n\n"
    for i, r in enumerate(rows, 1):
        m += f"{i}. `{r['nombre']}` — `{r['operaciones_total']} ops` | `{r['volumen_usdt']:.2f} USDT`\n"
    return m

def msg_clientes_riesgo():
    conn = get_conn()
    rows = conn.execute("""
        SELECT contraparte, COUNT(*) as cnt, SUM(monto) as total
        FROM cuentas_pendientes
        WHERE tipo='CXC' AND estado='Pendiente'
        GROUP BY contraparte ORDER BY total DESC LIMIT 5
    """).fetchall()
    conn.close()
    if not rows: return "✅ Sin clientes en riesgo (sin CXC pendiente)."
    m = "⚠️ *CLIENTES CON CXC PENDIENTE*\n\n"
    for r in rows:
        m += f"🔴 `{r['contraparte']}` — `{r['cnt']} deudas` | `{r['total']:,.2f}`\n"
    return m

# ══════════════════════════════════════════════════════════════════════
# BASE DE DATOS — FUNCIONES EXISTENTES
# ══════════════════════════════════════════════════════════════════════
def calcular_usdt_equiv(moneda, monto, pat_bs=0, dol_obs=0):
    if not monto: return 0.0
    if moneda in ('USDT','USD','USDC'): return float(monto)
    t = get_ultima_tasa()
    if moneda == 'BS':
        tasa = pat_bs or ((t.get('ban_bs_compra',0) or 0 + (t.get('ban_bs_venta',0) or 0))/2) or 1
        return round(float(monto)/tasa, 4) if tasa else 0
    if moneda == 'CLP':
        tasa = dol_obs or t.get('dolar_obs',0) or 1
        return round(float(monto)/tasa, 4) if tasa else 0
    if moneda == 'COP':
        tasa = t.get('trm',0) or 1
        return round(float(monto)/tasa, 4) if tasa else 0
    return float(monto)

def get_ultima_tasa():
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasas ORDER BY fecha_hora DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else {}

def calcular_limites(mejor_venta, dol_obs, western):
    limites = {}; tasas = {}
    if mejor_venta and dol_obs:
        limites['clp_bs'] = (mejor_venta*(1-FEE_USDT_BS))/(dol_obs*(1+FEE_USDT_CLP))
    if western:
        limites['clp_cop'] = western*(1-FEE_WU)
    if limites.get('clp_bs') and limites.get('clp_cop'):
        limites['bs_cop'] = limites['clp_cop']/limites['clp_bs']
    if limites.get('clp_bs'):
        tasas['clp_bs'] = round(limites['clp_bs']*(1-FEE_CLP_BS),6)
        tasas['bs_clp'] = round(limites['clp_bs']*(1+FEE_BS_CLP),6)
    if limites.get('clp_cop'):
        tasas['clp_cop'] = round(limites['clp_cop']*(1-FEE_CLP_COP),4)
        tasas['cop_clp'] = round(limites['clp_cop']*(1+FEE_COP_CLP),4)
    if limites.get('bs_cop'):
        tasas['cop_bs'] = round(limites['bs_cop']*(1-FEE_COP_BS),4)
        tasas['bs_cop'] = round(limites['bs_cop']*(1+FEE_BS_COP),4)
    return limites, tasas

def consultar_y_guardar(western_rate=None):
    ban_c,ban_v,ban_s = get_binance_banco_promedio("Banesco")
    mer_c,mer_v,mer_s = get_binance_banco_promedio("Mercantil")
    clp_c,clp_v = get_binance_fiat_promedio("CLP")
    cop_c,cop_v = get_binance_fiat_promedio("COP")
    dol_obs = get_dolar_observado()
    trm     = get_trm()
    bcv_usd,bcv_eur = get_bcv()
    mejor = "Mercantil" if (mer_s or 0) > (ban_s or 0) else "Banesco"
    mejor_venta = mer_v if mejor=="Mercantil" else ban_v
    limites,tasas = calcular_limites(mejor_venta, dol_obs, western_rate)
    datos = {
        'bcv_usd':bcv_usd,'bcv_eur':bcv_eur,
        'ban_bs_compra':ban_c,'ban_bs_venta':ban_v,'ban_bs_spread':ban_s,
        'mer_bs_compra':mer_c,'mer_bs_venta':mer_v,'mer_bs_spread':mer_s,
        'clp_compra':clp_c,'clp_venta':clp_v,'cop_compra':cop_c,'cop_venta':cop_v,
        'trm':trm,'dolar_obs':dol_obs,'western':western_rate,
        'limite_clp_bs':limites.get('clp_bs'),'limite_clp_cop':limites.get('clp_cop'),
        'limite_bs_cop':limites.get('bs_cop'),
        'tasa_gsa_clp_bs':tasas.get('clp_bs'),'tasa_gsa_bs_clp':tasas.get('bs_clp'),
        'tasa_gsa_clp_cop':tasas.get('clp_cop'),'tasa_gsa_cop_clp':tasas.get('cop_clp'),
        'tasa_gsa_cop_bs':tasas.get('cop_bs'),'tasa_gsa_bs_cop':tasas.get('bs_cop'),
        'mejor_banco':mejor,
    }
    # Guardar en DB
    if USE_SUPABASE:
        supa_insert('tasas', {k: v for k, v in datos.items() if k != 'mejor_banco' and v is not None})
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO tasas (
        bcv_usd,bcv_eur,ban_bs_compra,ban_bs_venta,ban_bs_spread,
        mer_bs_compra,mer_bs_venta,mer_bs_spread,clp_compra,clp_venta,
        cop_compra,cop_venta,trm,dolar_obs,western,
        limite_clp_bs,limite_clp_cop,limite_bs_cop,
        tasa_gsa_clp_bs,tasa_gsa_bs_clp,tasa_gsa_clp_cop,
        tasa_gsa_cop_clp,tasa_gsa_cop_bs,tasa_gsa_bs_cop
    ) VALUES (
        :bcv_usd,:bcv_eur,:ban_bs_compra,:ban_bs_venta,:ban_bs_spread,
        :mer_bs_compra,:mer_bs_venta,:mer_bs_spread,:clp_compra,:clp_venta,
        :cop_compra,:cop_venta,:trm,:dolar_obs,:western,
        :limite_clp_bs,:limite_clp_cop,:limite_bs_cop,
        :tasa_gsa_clp_bs,:tasa_gsa_bs_clp,:tasa_gsa_clp_cop,
        :tasa_gsa_cop_clp,:tasa_gsa_cop_bs,:tasa_gsa_bs_cop
    )""", datos)
    conn.commit(); conn.close()
    return datos

def guardar_operacion(datos):
    if USE_SUPABASE:
        supa_data = {k: str(v) if isinstance(v, (dict,list)) else v
                     for k, v in datos.items()
                     if k not in ('_tasa_sug','_mto_sal_sug','estado') and v is not None}
        supa_data['estado'] = datos.get('estado', 'Completada')
        supa_insert('operaciones', supa_data)
    conn = get_conn(); c = conn.cursor()
    datos['diferencial'] = (datos.get('tasa_cliente',0) or 0) - (datos.get('tasa_referencia',0) or 0)
    if not datos.get('usdt_equiv'):
        datos['usdt_equiv'] = calcular_usdt_equiv(
            datos.get('mon_entrada',''), datos.get('monto_entrada',0),
            datos.get('snap_pat_bs',0), datos.get('snap_dol_obs',0))
    keys = ['fecha','hora','cliente','referente','tipo_op','origen_fondos',
            'mon_entrada','monto_entrada','mon_salida','monto_salida',
            'tasa_cliente','tasa_referencia','usdt_equiv','diferencial',
            'metodo','corresponsal','traslado_bs','encomienda_cop',
            'repartidor','financiador','estado','observaciones',
            'cxc_pendiente','cxp_pendiente','snap_pat_bs','snap_dol_obs',
            'snap_trm','usuario_telegram']
    c.execute(f"""INSERT INTO operaciones ({','.join(keys)})
                  VALUES ({','.join([':'+k for k in keys])})""",
              {k: datos.get(k) for k in keys})
    op_id = c.lastrowid
    _actualizar_saldos_op(c, datos)
    _actualizar_cliente_db(c, datos)
    if datos.get('cxc_pendiente',0) > 0:
        c.execute("INSERT INTO cuentas_pendientes (tipo,contraparte,concepto,monto,moneda,vencimiento,op_origen_id) VALUES (?,?,?,?,?,date('now'),?)",
                  ('CXC',datos['cliente'],f"CXC Op#{op_id}",datos['cxc_pendiente'],datos['mon_entrada'],op_id))
    if datos.get('corresponsal') and datos.get('usdt_equiv',0) > 0:
        com = datos['usdt_equiv'] * 0.025
        c.execute("INSERT INTO cuentas_pendientes (tipo,contraparte,concepto,monto,moneda,vencimiento,op_origen_id) VALUES (?,?,?,?,'USDT',date('now','+7 days'),?)",
                  ('CXP',datos['corresponsal'],f"Comisión 2.5% Op#{op_id}",round(com,4),op_id))
    conn.commit(); conn.close()
    return op_id

def _actualizar_saldos_op(c, datos):
    tipo = datos.get('tipo_op','')
    mto_ent = datos.get('monto_entrada',0) or 0
    mto_sal = datos.get('monto_salida',0) or 0
    mapa = {
        'CLP→BS':('CLP_COPEC_PAY','BS_BANESCO'),'BS→CLP':('BS_BANESCO','CLP_COPEC_PAY'),
        'CLP→COP':('CLP_COPEC_PAY','COP_EFECTIVO_ORLANDO'),'COP→CLP':('COP_EFECTIVO_ORLANDO','CLP_COPEC_PAY'),
        'COP→BS':('COP_EFECTIVO_ORLANDO','BS_BANESCO'),'BS→COP':('BS_BANESCO','COP_EFECTIVO_ORLANDO'),
        'CLP→USDT':('CLP_COPEC_PAY','USDT_BINANCE'),'USDT→CLP':('USDT_BINANCE','CLP_COPEC_PAY'),
        'BS→USDT':('BS_BANESCO','USDT_BINANCE'),'USDT→BS':('USDT_BINANCE','BS_BANESCO'),
        'USD→CLP':('USD_EFECTIVO','CLP_COPEC_PAY'),'CLP→USD':('CLP_COPEC_PAY','USD_EFECTIVO'),
        'USD→BS':('USD_EFECTIVO','BS_BANESCO'),'BS→USD':('BS_BANESCO','USD_EFECTIVO'),
    }
    if tipo in mapa:
        ce, cs = mapa[tipo]
        c.execute("UPDATE saldos SET saldo=saldo-?,ultima_actualizacion=CURRENT_TIMESTAMP WHERE cuenta=?", (mto_ent,ce))
        c.execute("UPDATE saldos SET saldo=saldo+?,ultima_actualizacion=CURRENT_TIMESTAMP WHERE cuenta=?", (mto_sal,cs))

def _actualizar_cliente_db(c, datos):
    nombre = datos.get('cliente','')
    if not nombre or 'Binance' in nombre or 'GSA' in nombre: return
    usdt = datos.get('usdt_equiv',0) or 0
    c.execute("""INSERT INTO clientes (nombre,ultima_operacion,operaciones_total,volumen_usdt)
                 VALUES (?,date('now'),1,?)
                 ON CONFLICT(nombre) DO UPDATE SET
                 ultima_operacion=date('now'),
                 operaciones_total=operaciones_total+1,
                 volumen_usdt=volumen_usdt+excluded.volumen_usdt""", (nombre,usdt))

def get_saldos():
    conn = get_conn()
    rows = conn.execute("SELECT cuenta,moneda,saldo FROM saldos").fetchall()
    conn.close()
    return {r['cuenta']:{'moneda':r['moneda'],'saldo':r['saldo']} for r in rows}

def set_saldo(cuenta, saldo):
    conn = get_conn()
    conn.execute("INSERT INTO saldos (cuenta,moneda,saldo) VALUES (?,'',:s) ON CONFLICT(cuenta) DO UPDATE SET saldo=:s,ultima_actualizacion=CURRENT_TIMESTAMP",
                 {'cuenta':cuenta,'s':saldo})
    conn.commit(); conn.close()

def set_saldo_inicial(cuenta, saldo):
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO saldos_iniciales (cuenta,saldo,fecha) VALUES (?,?,date('now'))
                 ON CONFLICT(cuenta) DO UPDATE SET saldo=excluded.saldo, fecha=excluded.fecha""", (cuenta, saldo))
    movimiento = _calcular_movimiento_cuenta(c, cuenta)
    c.execute("UPDATE saldos SET saldo=?,ultima_actualizacion=CURRENT_TIMESTAMP WHERE cuenta=?",
              (saldo + movimiento, cuenta))
    conn.commit(); conn.close()

def _calcular_movimiento_cuenta(c, cuenta):
    mapa_entrada = {
        'BS_BANESCO': ["USDT→BS","COP→BS","USD→BS"], 'BS_MERCANTIL': [],
        'CLP_COPEC_PAY': ["BS→CLP","USDT→CLP","USD→CLP"],
        'COP_EFECTIVO_ORLANDO': ["BS→COP","CLP→COP"],
        'USDT_BINANCE': ["BS→USDT","CLP→USDT"], 'USD_EFECTIVO': ["BS→USD","CLP→USD"],
    }
    mapa_salida = {
        'BS_BANESCO': ["BS→CLP","BS→COP","BS→USDT","BS→USD"],
        'CLP_COPEC_PAY': ["CLP→BS","CLP→COP","CLP→USDT","CLP→USD"],
        'COP_EFECTIVO_ORLANDO': ["COP→BS","COP→CLP"],
        'USDT_BINANCE': ["USDT→BS","USDT→CLP"], 'USD_EFECTIVO': ["USD→BS","USD→CLP"],
    }
    entradas = mapa_entrada.get(cuenta, [])
    salidas  = mapa_salida.get(cuenta, [])
    total = 0.0
    if entradas:
        ph = ",".join(["?"]*len(entradas))
        rows = c.execute(f"SELECT COALESCE(SUM(monto_salida),0) FROM operaciones WHERE tipo_op IN ({ph}) AND estado='Completada'", entradas).fetchone()
        total += rows[0] if rows else 0
    if salidas:
        ph = ",".join(["?"]*len(salidas))
        rows = c.execute(f"SELECT COALESCE(SUM(monto_entrada),0) FROM operaciones WHERE tipo_op IN ({ph}) AND estado='Completada'", salidas).fetchone()
        total -= rows[0] if rows else 0
    return total

def get_cuentas_pendientes(tipo=None):
    conn = get_conn()
    if tipo:
        rows = conn.execute("SELECT * FROM cuentas_pendientes WHERE estado='Pendiente' AND tipo=? ORDER BY fecha",(tipo,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM cuentas_pendientes WHERE estado='Pendiente' ORDER BY tipo,fecha").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def marcar_pagado(cp_id):
    conn = get_conn()
    conn.execute("UPDATE cuentas_pendientes SET estado='Pagado' WHERE id=?",(cp_id,))
    conn.commit(); conn.close()

def get_resultados_hoy():
    conn = get_conn()
    hoy = str(today_local())
    row = conn.execute("SELECT COUNT(*) as ops,COALESCE(SUM(usdt_equiv),0) as vol,COALESCE(SUM(usdt_equiv*diferencial),0) as gan FROM operaciones WHERE fecha=? AND estado='Completada'", (hoy,)).fetchone()
    gas = conn.execute("SELECT COALESCE(SUM(usdt_equiv),0) as t FROM gastos WHERE fecha=?", (hoy,)).fetchone()
    conn.close()
    return {'ops':row['ops'],'volumen':row['vol'],'ganancia_operativa':row['gan'],'gastos':gas['t'],'ganancia_neta':row['gan']-gas['t']}

def get_resultados_mes():
    conn = get_conn()
    mes = now_local().strftime('%Y-%m')
    row = conn.execute("SELECT COUNT(*) as ops,COALESCE(SUM(usdt_equiv),0) as vol,COALESCE(SUM(usdt_equiv*diferencial),0) as gan FROM operaciones WHERE strftime('%Y-%m',fecha)=? AND estado='Completada'", (mes,)).fetchone()
    gas = conn.execute("SELECT COALESCE(SUM(usdt_equiv),0) as t FROM gastos WHERE strftime('%Y-%m',fecha)=?", (mes,)).fetchone()
    conn.close()
    return {'ops':row['ops'],'volumen':row['vol'],'ganancia_operativa':row['gan'],'gastos':gas['t'],'ganancia_neta':row['gan']-gas['t']}

def get_operaciones_hoy():
    conn = get_conn()
    hoy = str(today_local())
    rows = conn.execute("SELECT * FROM operaciones WHERE fecha=? ORDER BY hora", (hoy,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ══════════════════════════════════════════════════════════════════════
# MENSAJES TASAS Y SALDOS
# ══════════════════════════════════════════════════════════════════════
def fmt(v, d=2): return f"{v:,.{d}f}" if v else "N/D"

def spread_emoji(s):
    if s>=SPREAD_PREMIUM: return "🚀"
    if s>=SPREAD_BUENO:   return "🟢"
    if s>=SPREAD_MODERADO:return "🟡"
    return "🔴"

def construir_mensaje(d, es_especial=False):
    ahora = now_local().strftime("%d/%m/%Y — %I:%M %p")
    ban_s = d.get('ban_bs_spread',0) or 0
    mer_s = d.get('mer_bs_spread',0) or 0
    prefijo = "🔔 *TASA DE REFERENCIA*\n" if es_especial else ""
    m  = f"{prefijo}📊 *RESUMEN DE TASAS*\n📅 {ahora}\n━━━━━━━━━━━━━━━━━━━━\n\n"
    m += "🌎 *TASAS OFICIALES*\n\n"
    if d.get('trm'): m += f"🇨🇴  *TRM*\n      `{fmt(d['trm'])} COP`\n\n"
    if d.get('bcv_usd'): m += f"🏦  *USD/BCV*\n      `{fmt(d['bcv_usd'])} Bs`\n\n"
    if d.get('ban_bs_venta'):
        m += f"🏦  *Binance Banesco* {spread_emoji(ban_s)}\n      Compra: `{fmt(d['ban_bs_compra'])} Bs` | Venta: `{fmt(d['ban_bs_venta'])} Bs`\n      Spread: `{fmt(ban_s)} Bs`\n\n"
    if d.get('mer_bs_venta'):
        m += f"🏦  *Binance Mercantil* {spread_emoji(mer_s)}\n      Compra: `{fmt(d['mer_bs_compra'])} Bs` | Venta: `{fmt(d['mer_bs_venta'])} Bs`\n      Spread: `{fmt(mer_s)} Bs`\n\n"
    m += f"⭐ *Mejor opción: {d.get('mejor_banco','—')}*\n\n"
    if d.get('clp_venta'): m += f"🔵  *Binance USDT/CLP*\n      Compra: `{fmt(d['clp_compra'])} CLP` | Venta: `{fmt(d['clp_venta'])} CLP`\n\n"
    if d.get('cop_venta'): m += f"🔵  *Binance USDT/COP*\n      Compra: `{fmt(d['cop_compra'])} COP` | Venta: `{fmt(d['cop_venta'])} COP`\n\n"
    if d.get('dolar_obs'): m += f"🇨🇱  *Dólar Observado*\n      `{fmt(d['dolar_obs'])} CLP`\n\n"
    if d.get('western'): m += f"🌍  *Western Unión*\n      `{fmt(d['western'],4)} CLP/COP`\n\n"
    else: m += f"🌍  *Western Unión*\n      _Envía /western TASA_\n\n"
    m += f"━━━━━━━━━━━━━━━━━━━━\n💱 *GSA CAMBIOS*\n\n"
    if d.get('tasa_gsa_clp_bs'):
        m += f"🇨🇱➡️🇻🇪  CLP → Bs\n      `{fmt(d['tasa_gsa_clp_bs'],6)}`\n\n"
        m += f"🇻🇪➡️🇨🇱  Bs → CLP\n      `{fmt(d['tasa_gsa_bs_clp'],6)}`\n\n"
    if d.get('tasa_gsa_clp_cop'):
        m += f"🇨🇱➡️🇨🇴  CLP → COP\n      `{fmt(d['tasa_gsa_clp_cop'],4)}`\n\n"
        m += f"🇨🇴➡️🇨🇱  COP → CLP\n      `{fmt(d['tasa_gsa_cop_clp'],4)}`\n\n"
    if d.get('dolar_obs'):
        m += f"🇨🇱➡️🇺🇸  CLP → USD\n      `{fmt(d['dolar_obs']+SPREAD_CLP)} CLP`\n\n"
    m += f"━━━━━━━━━━━━━━━━━━━━\n📐 *LÍMITES OPERATIVOS*\n\n"
    if d.get('limite_clp_bs'): m += f"🔴  *Límite CLP/Bs*\n      `{fmt(d['limite_clp_bs'],6)}`\n\n"
    if d.get('limite_clp_cop'): m += f"🔴  *Límite CLP/COP*\n      `{fmt(d['limite_clp_cop'],4)}`\n\n"
    m += "━━━━━━━━━━━━━━━━━━━━"
    return m

GRUPOS_CUENTAS = {
    "🏦 CAJAS FÍSICAS":["COP_EFECTIVO_ORLANDO","USD_EFECTIVO"],
    "🇻🇪 BANCOS VENEZUELA":["BS_BANESCO","BS_MERCANTIL"],
    "🇨🇱 BANCOS CHILE":["CLP_COPEC_PAY","CLP_BANCOESTADO"],
    "🇨🇴 BANCOS COLOMBIA":["COP_BANCOLOMBIA_C1","COP_BANCOLOMBIA_C2","COP_NEQUI_C1","COP_NEQUI_C2","COP_NEQUI_C3"],
    "💎 WALLETS":["USDT_BINANCE","USDC_AIRTM"],
}

def get_moneda(cuenta):
    for m in ['BS','CLP','COP','USD','USDT','USDC']:
        if m in cuenta: return m
    return ''

def msg_saldos():
    saldos=get_saldos(); t=get_ultima_tasa()
    pat_bs=((t.get('ban_bs_compra',0) or 0)+(t.get('ban_bs_venta',0) or 0))/2 or 1
    dol_obs=t.get('dolar_obs',1) or 1
    ahora=now_local().strftime("%d/%m %I:%M %p")
    m=f"💰 *SALDOS GSA CAMBIOS*\n📅 {ahora}\n━━━━━━━━━━━━━━━━━━━━\n\n"
    patrimonio=0
    for grupo,cuentas in GRUPOS_CUENTAS.items():
        total_usdt=0; lineas=[]
        for cuenta in cuentas:
            info=saldos.get(cuenta,{}); saldo=info.get('saldo',0) or 0
            moneda=info.get('moneda','') or get_moneda(cuenta)
            usdt=calcular_usdt_equiv(moneda,saldo,pat_bs,dol_obs); total_usdt+=usdt
            nombre=NOMBRES_CUENTAS.get(cuenta,cuenta)
            if saldo!=0: lineas.append(f"  `{nombre:18s}` `{saldo:>12,.2f} {moneda}`")
        if lineas:
            m+=f"*{grupo}*\n"+"\n".join(lineas)+f"\n  Total: `{total_usdt:.2f} USDT`\n\n"
            patrimonio+=total_usdt
    m+=f"━━━━━━━━━━━━━━━━━━━━\n🏛️ *PATRIMONIO: `{patrimonio:.4f} USDT`*"
    return m

def msg_dashboard():
    hoy=get_resultados_hoy(); mes=get_resultados_mes()
    sald=get_saldos(); t=get_ultima_tasa()
    cxc=get_cuentas_pendientes('CXC'); cxp=get_cuentas_pendientes('CXP')
    pat_bs=((t.get('ban_bs_compra',0) or 0)+(t.get('ban_bs_venta',0) or 0))/2 or 1
    dol_obs=t.get('dolar_obs',1) or 1
    patrimonio=sum(calcular_usdt_equiv(info.get('moneda','') or get_moneda(k),info.get('saldo',0) or 0,pat_bs,dol_obs) for k,info in sald.items())
    ban_s=t.get('ban_bs_spread',0) or 0; mer_s=t.get('mer_bs_spread',0) or 0
    mejor_s=max(ban_s,mer_s)
    total_cxc=sum(c.get('monto',0) or 0 for c in cxc); total_cxp=sum(c.get('monto',0) or 0 for c in cxp)
    ahora=now_local().strftime("%d/%m/%Y %I:%M %p")
    m=f"📊 *GSA CAMBIOS — DASHBOARD*\n📅 {ahora}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    m+=f"📈 *HOY*\n  Ops: `{hoy['ops']}` | Vol: `{hoy['volumen']:.4f} USDT`\n  Ganancia: `{hoy['ganancia_neta']:.4f} USDT`\n\n"
    m+=f"📆 *MES*\n  Ops: `{mes['ops']}` | Ganancia: `{mes['ganancia_neta']:.4f} USDT`\n\n"
    m+=f"🏛️ *PATRIMONIO: `{patrimonio:.4f} USDT`*\n\n"
    senal="🟢 OPERAR" if mejor_s>=10 else "🟡 PRECAUCIÓN" if mejor_s>=7 else "🔴 NO OPERAR"
    m+=f"💱 *MERCADO:* {senal} (spread {mejor_s} BS)\n\n"
    if total_cxc>0: m+=f"⚠️ CXC: `{total_cxc:,.2f}` ({len(cxc)} registros)\n"
    if total_cxp>0: m+=f"⚠️ CXP: `{total_cxp:,.4f}` ({len(cxp)} registros)\n"
    bs=(sald.get('BS_BANESCO',{}).get('saldo',0) or 0)+(sald.get('BS_MERCANTIL',{}).get('saldo',0) or 0)
    clp=sald.get('CLP_COPEC_PAY',{}).get('saldo',0) or 0
    usdt=sald.get('USDT_BINANCE',{}).get('saldo',0) or 0
    m+=f"\n💰 *SALDOS CLAVE*\n  BS: `{bs:,.2f}` | CLP: `{clp:,.2f}` | USDT: `{usdt:.4f}`\n\n"
    m+="_/capital para análisis completo_"
    return m

def msg_cxc():
    cxcs=get_cuentas_pendientes('CXC')
    if not cxcs: return "✅ *No hay cuentas por cobrar pendientes.*"
    m="📋 *CXC — POR COBRAR*\n\n"; total=0
    for c in cxcs:
        m+=f"*#{c['id']}* — {c['contraparte']}\n  `{c['monto']:,.2f} {c['moneda']}` — {c['concepto']}\n\n"
        total+=c.get('monto',0) or 0
    m+=f"*Total: `{total:,.2f}`*\n_/cobrado ID para marcar_"
    return m

def msg_cxp():
    cxps=get_cuentas_pendientes('CXP')
    if not cxps: return "✅ *No hay cuentas por pagar pendientes.*"
    m="📋 *CXP — POR PAGAR*\n\n"; total=0
    for c in cxps:
        m+=f"*#{c['id']}* — {c['contraparte']}\n  `{c['monto']:,.4f} {c['moneda']}` — {c['concepto']}\n\n"
        total+=c.get('monto',0) or 0
    m+=f"*Total: `{total:,.4f}`*\n_/pagado ID para marcar_"
    return m

def msg_saldos_iniciales():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT cuenta,saldo,fecha FROM saldos_iniciales ORDER BY cuenta").fetchall()
        if not rows: return "No hay saldos iniciales.\n\nUsa: `/saldo_inicial BS_BANESCO 303581.42`"
        m = "📋 *SALDOS INICIALES*\n\n"
        for row in rows:
            nombre = NOMBRES_CUENTAS.get(row['cuenta'], row['cuenta'])
            m += f"`{nombre}`: `{row['saldo']:,.2f}` (desde {row['fecha']})\n"
        m += "\n_Usa /saldo_inicial CUENTA MONTO para corregir_"
        return m
    except: return "Tabla no encontrada."
    finally: conn.close()

# ══════════════════════════════════════════════════════════════════════
# IMPORTADOR BINANCE C2C
# ══════════════════════════════════════════════════════════════════════
def importar_c2c_inteligente(ruta_archivo, db_path, usuario='importacion'):
    import sqlite3 as _sq3
    from datetime import datetime as _dt

    _conn = _sq3.connect(db_path)
    _conn.execute("""CREATE TABLE IF NOT EXISTS debug_log
        (id INTEGER PRIMARY KEY AUTOINCREMENT, ts DATETIME DEFAULT CURRENT_TIMESTAMP, msg TEXT)""")
    _conn.execute("""CREATE TABLE IF NOT EXISTS binance_sesiones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sesion TEXT, fecha DATE, hora_inicio TEXT, hora_fin TEXT,
        compras INTEGER DEFAULT 0, ventas INTEGER DEFAULT 0,
        usdt_comprado REAL DEFAULT 0, bs_pagado REAL DEFAULT 0,
        usdt_vendido REAL DEFAULT 0, bs_recibido REAL DEFAULT 0,
        cpp_bs REAL DEFAULT 0, precio_venta_bs REAL DEFAULT 0,
        ganancia_bs REAL DEFAULT 0, ganancia_usdt REAL DEFAULT 0,
        usdt_pendiente REAL DEFAULT 0, fees_usdt REAL DEFAULT 0,
        estado TEXT DEFAULT 'Cerrado',
        fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    _conn.commit()

    def _log(msg):
        _conn.execute("INSERT INTO debug_log (msg) VALUES (?)", (msg,))
        _conn.commit()

    def _f(v):
        if v is None: return 0.0
        s = str(v).strip().strip("'")
        try: return float(s.replace(',','')) if s else 0.0
        except: return 0.0

    try:
        from openpyxl import load_workbook as _lw
        _wb = _lw(ruta_archivo, data_only=True)
        _ws = _wb.active
        _log(f"file_opened: rows={_ws.max_row}")
    except Exception as e:
        _log(f"file_error: {e}"); _conn.close()
        return {'error': str(e), 'importadas_maker':0,'importadas_taker':0,
                'importadas_clp':0,'omitidas':0,'errores':0,'sesiones':[],
                'total_ganancia_bs':0,'total_ganancia_u':0,'usdt_pendiente':0,'fees_total':0}

    _header = 11
    for _i, _row in enumerate(_ws.iter_rows(values_only=True), 1):
        for _v in _row:
            if _v and 'Order Number' in str(_v):
                _header = _i + 1; break
        if _header != 11: break

    _ordenes = []
    _skip_status = 0; _skip_date = 0; _skip_nonum = 0
    for _row in _ws.iter_rows(min_row=_header, values_only=True):
        if not _row[2]: _skip_nonum+=1; continue
        _st = str(_row[13]).strip().strip("'") if _row[13] else ''
        if _st != 'Completed': _skip_status+=1; continue
        _cr = str(_row[14]).strip().strip("'") if _row[14] else ''
        try:
            _fs = '20'+_cr if _cr.startswith('26-') else _cr
            _dt2 = _dt.strptime(_fs[:16], '%Y-%m-%d %H:%M')
        except: _skip_date+=1; continue
        _tf = _f(_row[11]); _mf = _f(_row[10])
        _ordenes.append({
            'num': str(_row[2]).strip().strip("'"),
            'tipo': str(_row[3]).strip().strip("'"),
            'fiat': str(_row[5]).strip().strip("'"),
            'total':_f(_row[6]),'precio':_f(_row[7]),'cantidad':_f(_row[8]),
            'maker_fee':_mf,'taker_fee':_tf,
            'contra':str(_row[12]).strip().strip("'") if _row[12] else '',
            'dt':_dt2,'is_taker':_tf>0,'is_maker':_tf==0,
        })

    _maker = [o for o in _ordenes if o['fiat']=='VES' and o['is_maker']]
    _taker = [o for o in _ordenes if o['is_taker']]
    _clp   = [o for o in _ordenes if o['fiat']=='CLP' and not o['is_taker']]

    _sesiones_raw = []
    if _maker:
        _sa = [_maker[0]]
        for _o in _maker[1:]:
            _gap = (_o['dt']-_sa[-1]['dt']).total_seconds()/60
            if _gap > PAUSA_SESION_MIN: _sesiones_raw.append(_sa); _sa=[_o]
            else: _sa.append(_o)
        if _sa: _sesiones_raw.append(_sa)

    _imp=0; _omit=0; _err=0; _ses_saved=[]
    for _ns, _ords in enumerate(_sesiones_raw, 1):
        _comp=[o for o in _ords if o['tipo']=='Buy']
        _vent=[o for o in _ords if o['tipo']=='Sell']
        _bsp=sum(o['total'] for o in _comp); _uc=sum(o['cantidad'] for o in _comp)
        _bsr=sum(o['total'] for o in _vent); _uv=sum(o['cantidad'] for o in _vent)
        _fees=sum(o['maker_fee']+o['taker_fee'] for o in _ords)
        _cpp=_bsp/_uc if _uc else 0; _pv=_bsr/_uv if _uv else 0
        _gb=_bsr-(_uv*_cpp) if _uv and _cpp else 0
        _gu=_gb/_cpp if _cpp else 0; _pend=_uc-_uv
        _fd=_ords[0]['dt'].strftime('%Y-%m-%d'); _hi=_ords[0]['dt'].strftime('%H:%M')
        _hf=_ords[-1]['dt'].strftime('%H:%M'); _sl=f"S{_ns}"
        _est='Abierto' if _pend>0.01 else 'Cerrado'

        _ex=_conn.execute("SELECT id FROM binance_sesiones WHERE sesion=? AND fecha=?",(_sl,_fd)).fetchone()
        if _ex:
            _conn.execute("""UPDATE binance_sesiones SET
                compras=?,ventas=?,usdt_comprado=?,bs_pagado=?,usdt_vendido=?,bs_recibido=?,
                cpp_bs=?,precio_venta_bs=?,ganancia_bs=?,ganancia_usdt=?,usdt_pendiente=?,
                fees_usdt=?,estado=?,hora_fin=? WHERE sesion=? AND fecha=?""",
                (len(_comp),len(_vent),round(_uc,4),round(_bsp,2),round(_uv,4),round(_bsr,2),
                 round(_cpp,4),round(_pv,4),round(_gb,2),round(_gu,4),round(_pend,4),
                 round(_fees,4),_est,_hf,_sl,_fd))
        else:
            _conn.execute("""INSERT INTO binance_sesiones
                (sesion,fecha,hora_inicio,hora_fin,compras,ventas,usdt_comprado,bs_pagado,
                 usdt_vendido,bs_recibido,cpp_bs,precio_venta_bs,ganancia_bs,ganancia_usdt,
                 usdt_pendiente,fees_usdt,estado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (_sl,_fd,_hi,_hf,len(_comp),len(_vent),round(_uc,4),round(_bsp,2),
                 round(_uv,4),round(_bsr,2),round(_cpp,4),round(_pv,4),round(_gb,2),
                 round(_gu,4),round(_pend,4),round(_fees,4),_est))
        _conn.commit()

        if USE_SUPABASE:
            ses_data = {'sesion':_sl,'fecha':_fd,'hora_inicio':_hi,'hora_fin':_hf,
                'compras':len(_comp),'ventas':len(_vent),'usdt_comprado':round(_uc,4),
                'bs_pagado':round(_bsp,2),'usdt_vendido':round(_uv,4),'bs_recibido':round(_bsr,2),
                'cpp_bs':round(_cpp,4),'precio_venta_bs':round(_pv,4),'ganancia_bs':round(_gb,2),
                'ganancia_usdt':round(_gu,4),'usdt_pendiente':round(_pend,4),
                'fees_usdt':round(_fees,4),'estado':_est}
            existing = supa_select('binance_sesiones',f'sesion=eq.{_sl}&fecha=eq.{_fd}')
            if existing: supa_update('binance_sesiones','sesion',_sl,ses_data)
            else: supa_insert('binance_sesiones',ses_data)

        for _o in _ords:
            _ex2=_conn.execute("SELECT id FROM operaciones WHERE observaciones LIKE ?",(f'%{_o["num"]}%',)).fetchone()
            if _ex2: _omit+=1; continue
            if _o['tipo']=='Buy':
                _top='BS→USDT';_me='BS';_ment=_o['total'];_ms='USDT';_msal=_o['cantidad']-_o['maker_fee']
            else:
                _top='USDT→BS';_me='USDT';_ment=_o['cantidad'];_ms='BS';_msal=_o['total']
            try:
                _conn.execute("""INSERT INTO operaciones
                    (fecha,hora,cliente,tipo_op,mon_entrada,monto_entrada,mon_salida,monto_salida,
                     tasa_cliente,tasa_referencia,usdt_equiv,diferencial,metodo,estado,observaciones,usuario_telegram)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (_o['dt'].strftime('%Y-%m-%d'),_o['dt'].strftime('%H:%M'),
                     f'Binance Maker ({_o["contra"]})',_top,_me,_ment,_ms,_msal,
                     _o['precio'],_o['precio'],_o['cantidad'],0,
                     f'Binance Maker — {_sl}','Completada',
                     f'Orden #{_o["num"]} | {_sl}',usuario))
                _imp+=1
                if USE_SUPABASE:
                    supa_insert('operaciones',{
                        'fecha':_o['dt'].strftime('%Y-%m-%d'),'hora':_o['dt'].strftime('%H:%M'),
                        'cliente':f'Binance Maker ({_o["contra"]})','tipo_op':_top,
                        'mon_entrada':_me,'monto_entrada':_ment,'mon_salida':_ms,'monto_salida':_msal,
                        'tasa_cliente':_o['precio'],'tasa_referencia':_o['precio'],
                        'usdt_equiv':_o['cantidad'],'diferencial':0,
                        'metodo':f'Binance Maker — {_sl}','estado':'Completada',
                        'observaciones':f'Orden #{_o["num"]} | {_sl}','usuario_telegram':usuario})
            except Exception as _ie: _err+=1; _log(f"insert_err: {_ie}")
        _conn.commit()
        _ses_saved.append({'sesion':_sl,'fecha':_fd,'hora_ini':_hi,'hora_fin':_hf,
            'compras':len(_comp),'ventas':len(_vent),'usdt_comp':_uc,'bs_pagado':_bsp,
            'usdt_vend':_uv,'bs_recibido':_bsr,'cpp':_cpp,'pv':_pv,
            'gan_bs':_gb,'gan_u':_gu,'pend':_pend,'fees':_fees,'estado':_est})

    # Taker
    _timp=0
    for _o in _taker:
        _ex=_conn.execute("SELECT id FROM operaciones WHERE observaciones LIKE ?",(f'%{_o["num"]}%',)).fetchone()
        if _ex: _omit+=1; continue
        _fiat=_o['fiat']
        if _fiat=='VES':
            if _o['tipo']=='Buy': _top='BS→USDT';_me='BS';_ment=_o['total'];_ms='USDT';_msal=_o['cantidad']-_o['taker_fee']
            else: _top='USDT→BS';_me='USDT';_ment=_o['cantidad'];_ms='BS';_msal=_o['total']
        elif _fiat=='CLP':
            if _o['tipo']=='Buy': _top='CLP→USDT';_me='CLP';_ment=_o['total'];_ms='USDT';_msal=_o['cantidad']-_o['taker_fee']
            else: _top='USDT→CLP';_me='USDT';_ment=_o['cantidad'];_ms='CLP';_msal=_o['total']
        else: continue
        try:
            _conn.execute("""INSERT INTO operaciones
                (fecha,hora,cliente,tipo_op,mon_entrada,monto_entrada,mon_salida,monto_salida,
                 tasa_cliente,tasa_referencia,usdt_equiv,diferencial,metodo,estado,observaciones,usuario_telegram)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (_o['dt'].strftime('%Y-%m-%d'),_o['dt'].strftime('%H:%M'),
                 f'Binance Taker ({_o["contra"]})',_top,_me,_ment,_ms,_msal,
                 _o['precio'],_o['precio'],_o['cantidad'],0,
                 'Binance P2P Taker','Completada',f'Orden #{_o["num"]} | Taker',usuario))
            _timp+=1
        except: pass

    # CLP
    _cimp=0
    for _o in _clp:
        _ex=_conn.execute("SELECT id FROM operaciones WHERE observaciones LIKE ?",(f'%{_o["num"]}%',)).fetchone()
        if _ex: continue
        if _o['tipo']=='Buy': _top='CLP→USDT';_me='CLP';_ment=_o['total'];_ms='USDT';_msal=_o['cantidad']-_o['maker_fee']
        else: _top='USDT→CLP';_me='USDT';_ment=_o['cantidad'];_ms='CLP';_msal=_o['total']
        try:
            _conn.execute("""INSERT INTO operaciones
                (fecha,hora,cliente,tipo_op,mon_entrada,monto_entrada,mon_salida,monto_salida,
                 tasa_cliente,tasa_referencia,usdt_equiv,diferencial,metodo,estado,observaciones,usuario_telegram)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (_o['dt'].strftime('%Y-%m-%d'),_o['dt'].strftime('%H:%M'),
                 f'Binance CLP ({_o["contra"]})',_top,_me,_ment,_ms,_msal,
                 _o['precio'],_o['precio'],_o['cantidad'],0,
                 'Binance P2P CLP','Completada',f'Orden #{_o["num"]} | CLP',usuario))
            _cimp+=1
        except: pass

    _conn.commit(); _conn.close()
    _tgb=sum(s['gan_bs'] for s in _ses_saved)
    _tgu=sum(s['gan_u'] for s in _ses_saved)
    _tpend=sum(s['pend'] for s in _ses_saved if s['estado']=='Abierto')
    _tfees=sum(s['fees'] for s in _ses_saved)
    return {'sesiones':_ses_saved,'importadas_maker':_imp,'importadas_taker':_timp,
            'importadas_clp':_cimp,'omitidas':_omit,'errores':_err,
            'total_ganancia_bs':round(_tgb,2),'total_ganancia_u':round(_tgu,4),
            'usdt_pendiente':round(_tpend,4),'fees_total':round(_tfees,4)}

def formatear_resultado_inteligente(resultado):
    if 'error' in resultado: return f"❌ Error: {resultado['error']}"
    ses = resultado['sesiones']
    ses_mostrar = ses[-10:] if len(ses) > 10 else ses
    m = f"✅ *IMPORTACIÓN BINANCE C2C*\n\n"
    if len(ses) > 10: m += f"_{len(ses)} sesiones — mostrando últimas 10_\n\n"
    m += "📊 *SESIONES DE ARBITRAJE (Maker)*\n\n"
    for s in ses_mostrar:
        emoji = "🟡" if s['estado']=='Abierto' else "🟢"
        m += f"{emoji} *{s['sesion']}* — {s['fecha']} {s['hora_ini']}→{s['hora_fin']}\n"
        m += f"  Compras: `{s['compras']}` | Ventas: `{s['ventas']}`\n"
        m += f"  CPP: `{s['cpp']:.2f} BS` | Venta: `{s['pv']:.2f} BS`\n"
        if s['gan_bs'] != 0: m += f"  Ganancia: `{s['gan_bs']:.2f} BS` (`{s['gan_u']:.4f} USDT`)\n"
        if s['pend'] > 0.01: m += f"  ⚠️ Pendiente inventario: `{s['pend']:.4f} USDT`\n"
        m += "\n"
    m += "━━━━━━━━━━━━━━━━━━━━\n*TOTAL*\n"
    m += f"  Ganancia: `{resultado['total_ganancia_bs']:.2f} BS` (`{resultado['total_ganancia_u']:.4f} USDT`)\n"
    if resultado['usdt_pendiente'] > 0:
        m += f"  📦 USDT en inventario: `{resultado['usdt_pendiente']:.4f} USDT`\n"
    m += f"  Fees: `{resultado['fees_total']:.4f} USDT`\n\n"
    if resultado['importadas_taker'] > 0: m += f"🔄 Taker: `{resultado['importadas_taker']}`\n"
    if resultado['importadas_clp'] > 0: m += f"🇨🇱 CLP: `{resultado['importadas_clp']}`\n"
    total = resultado['importadas_maker']+resultado['importadas_taker']+resultado['importadas_clp']
    m += f"\n📥 Importadas: `{total}` | Omitidas: `{resultado['omitidas']}`"
    return m

# ══════════════════════════════════════════════════════════════════════
# CONVERSACIÓN /operacion
# ══════════════════════════════════════════════════════════════════════
conversaciones = {}

def iniciar_operacion(chat_id):
    conversaciones[chat_id] = {'paso':-1,'datos':{
        'fecha':str(today_local()),
        'hora':hora_local(),
        'usuario_telegram':str(chat_id),'estado':'Completada',
        'traslado_bs':0,'encomienda_cop':0,'cxc_pendiente':0,'cxp_pendiente':0,
        'repartidor':'Cristofer Ruiz',
    }}
    tipos = "\n".join([f"  `{t}`" for t in TIPOS_OP])
    return f"💱 *NUEVA OPERACIÓN*\n\n¿Tipo de operación?\n\n{tipos}\n\n_/cancelar para salir_"

def procesar_conv(chat_id, texto):
    if chat_id not in conversaciones: return "No hay operación activa. Usa /operacion para iniciar."
    conv=conversaciones[chat_id]; paso=conv['paso']; datos=conv['datos']
    if texto.lower() in ('/cancelar','cancelar'):
        del conversaciones[chat_id]; return "❌ Operación cancelada."

    if paso==-1:
        hoy = today_local(); ayer = hoy - datetime.timedelta(days=1)
        if texto.lower() in ('hoy','today','h'): datos['fecha'] = str(hoy)
        elif texto.lower() in ('ayer','yesterday','a'): datos['fecha'] = str(ayer)
        else:
            try:
                for fmt_str in ('%d/%m/%Y','%Y-%m-%d','%d-%m-%Y'):
                    try:
                        dt = datetime.datetime.strptime(texto, fmt_str)
                        datos['fecha'] = dt.strftime('%Y-%m-%d'); break
                    except: pass
                else: return "⚠️ Escribe *hoy*, *ayer*, o fecha como `05/06/2026`"
            except: return "⚠️ Fecha inválida."
        conv['paso'] = 0
        tipos = "\n".join([f"  `{t}`" for t in TIPOS_OP])
        return f"💱 *NUEVA OPERACIÓN*\nFecha: `{datos['fecha']}`\n\n¿Tipo de operación?\n\n{tipos}\n\n_/cancelar para salir_"

    if paso==0:
        if texto not in TIPOS_OP: return "⚠️ Selecciona un tipo válido de la lista."
        datos['tipo_op']=texto
        partes=texto.replace('→','-').split('-')
        if len(partes)==2: datos['mon_entrada']=partes[0]; datos['mon_salida']=partes[1]
        conv['paso']=1; return "👤 ¿Nombre del cliente?"
    elif paso==1:
        datos['cliente']=texto; conv['paso']=2
        return f"💰 ¿Cuánto {datos.get('mon_entrada','?')} entrega el cliente?"
    elif paso==2:
        try:
            datos['monto_entrada']=float(texto.replace(',','.'))
            t=get_ultima_tasa(); tasa_sug=_tasa_sug(datos['tipo_op'],t)
            if tasa_sug:
                datos['_tasa_sug']=tasa_sug
                mto_sal=_calc_sal(datos['tipo_op'],datos['monto_entrada'],tasa_sug)
                datos['_mto_sal_sug']=mto_sal; conv['paso']=3
                return f"📊 Tasa sugerida: `{tasa_sug}`\nCliente recibe: `{mto_sal:,.2f} {datos.get('mon_salida','?')}`\n\nEscribe *usar* para confirmar o ingresa otra tasa."
            conv['paso']=3; return f"💰 ¿Cuánto {datos.get('mon_salida','?')} recibe el cliente?"
        except: return "⚠️ Ingresa un número válido."
    elif paso==3:
        if texto.lower() in ('usar','si','sí','ok','s'):
            datos['tasa_cliente']=datos.get('_tasa_sug',0)
            datos['monto_salida']=datos.get('_mto_sal_sug',0)
        else:
            try:
                val=float(texto.replace(',','.')); datos['tasa_cliente']=val
                datos['monto_salida']=_calc_sal(datos['tipo_op'],datos['monto_entrada'],val)
            except: return "⚠️ Ingresa la tasa como número o escribe *usar*"
        t=get_ultima_tasa()
        datos['snap_pat_bs']=((t.get('ban_bs_compra',0) or 0)+(t.get('ban_bs_venta',0) or 0))/2
        datos['snap_dol_obs']=t.get('dolar_obs',0) or 0
        datos['snap_trm']=t.get('trm',0) or 0
        datos['usdt_equiv']=calcular_usdt_equiv(datos['mon_entrada'],datos['monto_entrada'],datos['snap_pat_bs'],datos['snap_dol_obs'])
        conv['paso']=4
        return "💳 ¿Método de pago?\n`Copec Pay` | `Bancolombia` | `Nequi` | `Efectivo` | `Airtm` | `Binance` | `Otro`"
    elif paso==4:
        datos['metodo']=texto; conv['paso']=5
        ops="\n".join([f"  `{c}`" for c in CORRESPONSALES])
        return f"🏦 ¿Corresponsal?\n{ops}\n\n_O escribe *no* si fue directo_"
    elif paso==5:
        datos['corresponsal']='' if texto.lower() in ('no','ninguno','directo') else texto
        conv['paso']=6; return "📦 ¿Hubo entrega física? (*si* o *no*)"
    elif paso==6:
        if texto.lower() in ('si','sí','s'):
            datos['entrega_fisica']='Sí'; conv['paso']=61
            return "💸 ¿Costo de traslado? (en COP o BS, o *0* si fue gratis)"
        datos['entrega_fisica']='No'; conv['paso']=7
        return "💳 ¿El cliente quedó debiendo? (*no*, *si*, o el monto)"
    elif paso==61:
        try:
            monto=float(texto.replace(',','.'))
            if monto>0:
                if monto>10000: datos['encomienda_cop']=monto
                else: datos['traslado_bs']=monto
            conv['paso']=7; return "💳 ¿El cliente quedó debiendo? (*no*, *si*, o el monto)"
        except: return "⚠️ Ingresa un número o *0*"
    elif paso==7:
        if texto.lower() in ('no','n','0'): datos['cxc_pendiente']=0
        elif texto.lower() in ('si','sí','s'):
            conv['paso']=71; return f"¿Cuánto {datos.get('mon_entrada','?')} debe el cliente?"
        else:
            try: datos['cxc_pendiente']=float(texto.replace(',','.'))
            except: return "Responde *si*, *no* o el monto."
        conv['paso']=8; return _resumen(datos)
    elif paso==71:
        try: datos['cxc_pendiente']=float(texto.replace(',','.')); conv['paso']=8; return _resumen(datos)
        except: return "⚠️ Ingresa el monto como número."
    elif paso==8:
        if texto.lower() in ('si','sí','s','confirmar','ok'):
            op_id=guardar_operacion(datos); del conversaciones[chat_id]
            m = f"✅ *Op #{op_id} registrada*\nCliente: `{datos['cliente']}`\nTipo: `{datos['tipo_op']}`\nUSDT: `{datos.get('usdt_equiv',0):.4f}`\n"
            if datos.get('cxc_pendiente',0)>0: m+=f"⚠️ CXC: `{datos['cxc_pendiente']:,.2f} {datos['mon_entrada']}`\n"
            m += "_Saldos actualizados_"; return m
        del conversaciones[chat_id]; return "❌ Operación cancelada."
    return "⚠️ Algo salió mal. Usa /operacion para reiniciar."

def _resumen(datos):
    m = f"📋 *CONFIRMAR*\n━━━━━━━━━━━━━━━━━━━━\n"
    m += f"Tipo: `{datos.get('tipo_op')}`\nCliente: `{datos.get('cliente')}`\n"
    m += f"Entrada: `{datos.get('monto_entrada',0):,.2f} {datos.get('mon_entrada')}`\n"
    m += f"Salida: `{datos.get('monto_salida',0):,.2f} {datos.get('mon_salida')}`\n"
    m += f"USDT: `{datos.get('usdt_equiv',0):.4f}`\n"
    if datos.get('cxc_pendiente',0)>0: m+=f"⚠️ CXC: `{datos['cxc_pendiente']:,.2f}`\n"
    m += "━━━━━━━━━━━━━━━━━━━━\n¿Confirmar? *si* o *no*"
    return m

def _tasa_sug(tipo, t):
    mapa={'CLP→BS':t.get('tasa_gsa_clp_bs'),'BS→CLP':t.get('tasa_gsa_bs_clp'),
          'CLP→COP':t.get('tasa_gsa_clp_cop'),'COP→CLP':t.get('tasa_gsa_cop_clp'),
          'COP→BS':t.get('tasa_gsa_cop_bs'),'BS→COP':t.get('tasa_gsa_bs_cop'),
          'CLP→USDT':t.get('clp_compra'),'USDT→CLP':t.get('clp_venta'),
          'BS→USDT':t.get('ban_bs_compra'),'USDT→BS':t.get('ban_bs_venta'),
          'USD→CLP':t.get('dolar_obs'),'USD→BS':t.get('ban_bs_venta')}
    return mapa.get(tipo)

def _calc_sal(tipo, mto, tasa):
    if not tasa: return 0
    if tipo in ('CLP→BS','COP→BS','USD→BS','CLP→COP','BS→CLP','BS→COP','BS→USD','USDT→CLP','USDT→BS'): return round(mto*tasa,2)
    if tipo in ('CLP→USDT','BS→USDT'): return round(mto/tasa,4)
    if tipo in ('COP→CLP',): return round(mto/tasa,2)
    return round(mto*tasa,2)

def hay_conv_activa(chat_id): return chat_id in conversaciones

# ══════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ══════════════════════════════════════════════════════════════════════
def exportar_csv():
    os.makedirs(CSV_EXPORT_PATH, exist_ok=True)
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    for tabla in ['tasas','operaciones','saldos','clientes','gastos','tesoreria',
                  'cuentas_pendientes','precios_historicos','binance_sesiones']:
        try:
            rows=conn.execute(f"SELECT * FROM {tabla}").fetchall()
            if not rows: continue
            ruta=os.path.join(CSV_EXPORT_PATH,f"{tabla}.csv")
            with open(ruta,'w',newline='',encoding='utf-8-sig') as f:
                w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader()
                w.writerows([dict(r) for r in rows])
        except: pass
    conn.close()
    print(f"✅ CSV exportados — {now_local().strftime('%H:%M:%S')}")

# ══════════════════════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════════════════════
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def send(chat_id, text, parse_mode="Markdown"):
    try:
        requests.post(f"{BASE_URL}/sendMessage", json={
            "chat_id":chat_id,"text":text,
            "parse_mode":parse_mode,"disable_web_page_preview":True}, timeout=10)
    except Exception as e: print(f"Error send: {e}")

def get_updates(offset=0):
    try:
        r=requests.get(f"{BASE_URL}/getUpdates",params={"offset":offset,"timeout":30},timeout=35)
        return r.json().get("result",[])
    except: return []

def download_file(file_id):
    try:
        r = requests.get(f"{BASE_URL}/getFile", params={"file_id": file_id}, timeout=10)
        file_path = r.json()["result"]["file_path"]
        r2 = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}", timeout=30)
        return r2.content
    except Exception as e:
        print(f"Error descargando archivo: {e}"); return None

# ══════════════════════════════════════════════════════════════════════
# PROCESADOR DE COMANDOS
# ══════════════════════════════════════════════════════════════════════
ultimo_offset=0
western_rate=None
ultimo_datos={}
ultimo_precio_bs_venta=0
ultimo_precio_clp=0
esperando_importar={}

def procesar(chat_id, texto):
    global western_rate, ultimo_datos

    if hay_conv_activa(chat_id) and not texto.startswith('/'):
        send(chat_id, procesar_conv(chat_id, texto)); return

    if chat_id in esperando_importar and not texto.startswith('/'):
        archivo=texto.strip()
        ruta=os.path.abspath(os.path.join(os.path.dirname(DB_PATH), archivo))
        send(chat_id, f"⏳ Procesando `{archivo}`...")
        resultado=importar_c2c_inteligente(ruta, DB_PATH, str(chat_id))
        send(chat_id, formatear_resultado_inteligente(resultado))
        del esperando_importar[chat_id]; return

    partes=texto.split(); cmd=partes[0].lower() if partes else ''

    # ── TASAS ──
    if cmd=='/tasas':
        send(chat_id,"⏳ Consultando tasas...")
        datos=consultar_y_guardar(western_rate); ultimo_datos=datos
        send(chat_id, construir_mensaje(datos))

    elif cmd=='/western':
        if len(partes)>=2:
            try:
                western_rate=float(partes[1].replace(',','.'))
                set_config('western_actualizado_hoy', str(today_local()))
                send(chat_id,f"✅ Western: `{western_rate}` — Recordatorio cancelado para hoy.")
            except: send(chat_id,"Uso: /western 0.0042")
        else: send(chat_id,"Uso: `/western 0.0042`")

    elif cmd=='/limites':
        t=ultimo_datos or {}
        m=f"📐 *LÍMITES*\nCLP/BS: `{t.get('limite_clp_bs','N/D')}`\nCLP/COP: `{t.get('limite_clp_cop','N/D')}`"
        send(chat_id,m)

    # ── MERCADO ──
    elif cmd=='/mercado':
        send(chat_id,"⏳ Consultando mercado en vivo...")
        send(chat_id, msg_mercado())

    # ── PATRÓN ──
    elif cmd=='/patron':
        sub = partes[1].lower() if len(partes)>1 else 'bs'
        if sub == 'bs':
            resultado = analizar_patron_bs()
            if resultado[0] is None:
                send(chat_id, resultado[1]); return
            resumen, mejor, peor = resultado
            m = "📊 *PATRÓN HISTÓRICO BS*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for hora, d in list(resumen.items())[:12]:
                bar = "🟢" if d['spread_prom'] >= SPREAD_MIN_ALERTA else "🔴"
                m += f"`{hora}` {bar} spread `{d['spread_prom']:.1f}` | venta `{d['venta_prom']:.2f} Bs`\n"
            m += f"\n🏆 Mejor hora: `{mejor[0]}` (spread prom `{mejor[1]['spread_prom']:.1f} Bs`)\n"
            m += f"📉 Peor hora: `{peor[0]}` (spread prom `{peor[1]['spread_prom']:.1f} Bs`)\n"
            send(chat_id, m)
        elif sub == 'semana':
            send(chat_id, generar_reporte_semanal())
        elif sub == 'hoy':
            send(chat_id, generar_reporte_diario())
        else:
            send(chat_id, "Uso: `/patron bs` | `/patron hoy` | `/patron semana`")

    # ── SIMULAR ──
    elif cmd=='/simular':
        if len(partes) >= 3:
            try:
                moneda = partes[1].upper()
                monto = float(partes[2].replace(',','.').replace('.','',monto.count('.')-1) if partes[2].count('.')>1 else partes[2].replace(',','.'))
                if moneda not in ('CLP','BS','USDT','BS'):
                    send(chat_id, "Monedas: CLP, BS, USDT"); return
                send(chat_id, "⏳ Calculando...")
                send(chat_id, simular_operacion(moneda, monto))
            except Exception as e:
                send(chat_id, f"Uso: `/simular CLP 500000`\nError: {e}")
        else:
            send(chat_id, "Uso: `/simular CLP 500000` o `/simular BS 300000`")

    # ── CAPITAL ──
    elif cmd=='/capital':
        send(chat_id, msg_capital())

    # ── UMBRAL ──
    elif cmd=='/umbral':
        if len(partes) >= 3:
            try:
                cuenta = partes[1].upper()
                monto = float(partes[2].replace(',','.'))
                if cuenta not in NOMBRES_CUENTAS:
                    send(chat_id, f"Cuenta no válida. Opciones:\n" + "\n".join([f"`{k}`" for k in NOMBRES_CUENTAS.keys()])); return
                moneda = get_moneda(cuenta)
                conn = get_conn()
                conn.execute("""INSERT INTO umbrales_liquidez (cuenta,umbral_minimo,moneda)
                    VALUES (?,?,?) ON CONFLICT(cuenta) DO UPDATE SET umbral_minimo=excluded.umbral_minimo""",
                    (cuenta, monto, moneda))
                conn.commit(); conn.close()
                nombre = NOMBRES_CUENTAS[cuenta]
                send(chat_id, f"✅ Umbral configurado\n`{nombre}`: mínimo `{monto:,.2f} {moneda}`")
            except: send(chat_id, "Uso: `/umbral CLP_COPEC_PAY 100000`")
        else:
            conn = get_conn()
            rows = conn.execute("SELECT * FROM umbrales_liquidez WHERE activo=1").fetchall()
            conn.close()
            if not rows: send(chat_id, "Sin umbrales configurados.\nUso: `/umbral CLP_COPEC_PAY 100000`"); return
            m = "⚙️ *UMBRALES CONFIGURADOS*\n\n"
            for r in rows:
                nombre = NOMBRES_CUENTAS.get(r['cuenta'], r['cuenta'])
                m += f"`{nombre}`: mín `{r['umbral_minimo']:,.2f} {r['moneda']}`\n"
            send(chat_id, m)

    # ── CLIENTES ──
    elif cmd=='/clientes':
        sub = partes[1].lower() if len(partes)>1 else 'top'
        if sub == 'top': send(chat_id, msg_clientes_top())
        elif sub == 'riesgo': send(chat_id, msg_clientes_riesgo())
        else: send(chat_id, "Uso: `/clientes top` | `/clientes riesgo`")

    elif cmd=='/resumen_corresponsal':
        if len(partes) >= 2:
            nombre = ' '.join(partes[1:])
            send(chat_id, msg_resumen_corresponsal(nombre))
        else:
            ops_lista = "\n".join([f"  `{c}`" for c in CORRESPONSALES])
            send(chat_id, f"Uso: `/resumen_corresponsal Bancolombia C1`\n\nCorresponsales:\n{ops_lista}")

    # ── OPERACIONES ──
    elif cmd=='/operacion': send(chat_id, iniciar_operacion(chat_id))
    elif cmd=='/cancelar':
        if hay_conv_activa(chat_id): procesar_conv(chat_id,'/cancelar'); send(chat_id,"❌ Cancelado.")
        elif chat_id in esperando_importar: del esperando_importar[chat_id]; send(chat_id,"❌ Cancelado.")
        else: send(chat_id,"No hay operación activa.")

    elif cmd=='/operaciones':
        ops=get_operaciones_hoy()
        if not ops: send(chat_id,"Sin operaciones hoy."); return
        m=f"📋 *HOY ({len(ops)} ops)*\n\n"
        for op in ops[-10:]:
            m+=f"*#{op['id']}* {op['tipo_op']} — {op['cliente']}\n  `{op['monto_entrada']:,.2f} {op['mon_entrada']}` → `{op['monto_salida']:,.2f} {op['mon_salida']}`\n\n"
        send(chat_id,m)

    elif cmd=='/ultima':
        ops=get_operaciones_hoy()
        if not ops: send(chat_id,"Sin operaciones hoy."); return
        op=ops[-1]
        m=f"📋 *ÚLTIMA*\n#{op['id']} | {op['tipo_op']}\nCliente: {op['cliente']}\nEntrada: `{op['monto_entrada']:,.2f} {op['mon_entrada']}`\nSalida: `{op['monto_salida']:,.2f} {op['mon_salida']}`\nEstado: {op['estado']}"
        send(chat_id,m)

    # ── SALDOS ──
    elif cmd in ('/saldo','/caja','/posicion'): send(chat_id, msg_saldos())
    elif cmd=='/dashboard': send(chat_id, msg_dashboard())
    elif cmd=='/resultado':
        d=get_resultados_mes()
        send(chat_id,f"💵 *P&L MES*\nOps: `{d['ops']}` | Vol: `{d['volumen']:.4f}`\nGanancia: `{d['ganancia_neta']:.4f} USDT`")
    elif cmd=='/ganancia':
        d=get_resultados_hoy()
        send(chat_id,f"💵 *GANANCIA HOY*\nOps: `{d['ops']}` | Vol: `{d['volumen']:.4f}`\nGanancia: `{d['ganancia_neta']:.4f} USDT`")
    elif cmd=='/cxc': send(chat_id, msg_cxc())
    elif cmd=='/cxp': send(chat_id, msg_cxp())
    elif cmd=='/cobrado':
        if len(partes)>=2:
            try: marcar_pagado(int(partes[1])); send(chat_id,f"✅ CXC #{partes[1]} marcada cobrada.")
            except: send(chat_id,"Uso: /cobrado ID")
    elif cmd=='/pagado':
        if len(partes)>=2:
            try: marcar_pagado(int(partes[1])); send(chat_id,f"✅ CXP #{partes[1]} marcada pagada.")
            except: send(chat_id,"Uso: /pagado ID")

    elif cmd=='/setsaldo':
        if len(partes)>=3:
            try:
                cuenta=partes[1].upper(); monto=float(partes[2].replace(',','.'))
                if cuenta not in NOMBRES_CUENTAS:
                    send(chat_id,f"⚠️ Cuenta no válida."); return
                set_saldo(cuenta,monto); nombre=NOMBRES_CUENTAS[cuenta]
                send(chat_id,f"✅ `{nombre}`: `{monto:,.2f}`")
            except: send(chat_id,"Uso: `/setsaldo BS_BANESCO 125430`")
        else:
            send(chat_id,"Uso: `/setsaldo CUENTA MONTO`\n\n"+"\n".join([f"`{k}`" for k in NOMBRES_CUENTAS]))

    elif cmd=='/saldo_inicial':
        if len(partes)>=3:
            try:
                cuenta=partes[1].upper(); monto=float(partes[2].replace(',','.'))
                if cuenta not in NOMBRES_CUENTAS:
                    send(chat_id,"⚠️ Cuenta no válida."); return
                set_saldo_inicial(cuenta,monto); nombre=NOMBRES_CUENTAS[cuenta]
                send(chat_id,f"✅ Saldo inicial `{nombre}`: `{monto:,.2f}`")
            except: send(chat_id,"Uso: `/saldo_inicial BS_BANESCO 303581.42`")
        else: send(chat_id,"Uso: `/saldo_inicial CUENTA MONTO`")

    elif cmd=='/saldos_iniciales': send(chat_id, msg_saldos_iniciales())

    # ── SISTEMA ──
    elif cmd=='/importar':
        esperando_importar[chat_id]=True
        send(chat_id,"📂 *IMPORTAR BINANCE C2C*\n\nEscribe el nombre del archivo .xlsx o súbelo directamente.\n_/cancelar para salir_")

    elif cmd=='/sync':
        send(chat_id,"⏳ Exportando CSV..."); exportar_csv()
        send(chat_id,"✅ CSV exportados para Excel.")

    elif cmd=='/version':
        supa_st = "✅ Conectado" if USE_SUPABASE else "❌ Desactivado"
        send(chat_id,f"🤖 *GSA Cambios Bot v6.0*\nInteligencia de Mercado activa\nSupabase: {supa_st}\nZona horaria: UTC{UTC_OFFSET}")

    elif cmd=='/testsupabase':
        sb_url=os.getenv("SUPABASE_URL","NO_URL"); sb_key=os.getenv("SUPABASE_KEY","NO_KEY")
        send(chat_id,f"🔍 *DEBUG SUPABASE*\nURL: `{sb_url[:40]}`\nKEY: `{sb_key[:20]}...`\nUSE_SUPABASE: `{USE_SUPABASE}`")
        if USE_SUPABASE:
            try:
                r=requests.get(f"{SUPABASE_URL}/rest/v1/tasas?select=count",
                    headers={"apikey":SUPABASE_KEY,"Authorization":f"Bearer {SUPABASE_KEY}"},timeout=10)
                send(chat_id,f"✅ Supabase responde: `{r.status_code}` — `{r.text[:100]}`")
            except Exception as e: send(chat_id,f"❌ Error: `{e}`")
        else: send(chat_id,"❌ USE_SUPABASE es False")

    elif cmd in ('/ayuda','/start','/help'):
        send(chat_id,"""🤖 *GSA CAMBIOS v6.0 — COMANDOS*

*📊 TASAS*
/tasas | /western TASA | /limites

*📡 MERCADO EN VIVO*
/mercado | /patron bs | /patron hoy | /patron semana

*🧮 SIMULADOR*
/simular CLP 500000 | /simular BS 300000

*💼 CAPITAL*
/capital | /umbral CUENTA MONTO

*💱 OPERACIONES*
/operacion | /operaciones | /ultima

*💰 SALDOS*
/saldo | /caja | /posicion

*📈 RESULTADOS*
/dashboard | /resultado | /ganancia

*📋 PENDIENTES*
/cxc | /cxp | /cobrado ID | /pagado ID

*👥 CLIENTES*
/clientes top | /clientes riesgo
/resumen_corresponsal NOMBRE

*⚙️ SISTEMA*
/importar | /sync | /saldo_inicial CUENTA MONTO
/setsaldo CUENTA MONTO | /testsupabase | /version""")

    elif hay_conv_activa(chat_id):
        send(chat_id, procesar_conv(chat_id, texto))

# ══════════════════════════════════════════════════════════════════════
# PROCESADOR DE DOCUMENTOS
# ══════════════════════════════════════════════════════════════════════
def procesar_documento(chat_id, file_id, nombre):
    nombre_lower = nombre.lower()
    if not (nombre_lower.endswith('.xlsx') or nombre_lower.endswith('.csv')):
        send(chat_id, f"⚠️ Solo acepto .xlsx o .csv\nRecibí: `{nombre}`"); return

    send(chat_id, f"⏳ Procesando `{nombre}`...")
    contenido = download_file(file_id)
    if not contenido:
        send(chat_id, "❌ No pude descargar el archivo."); return

    import tempfile
    if nombre_lower.endswith('.csv'):
        try:
            import csv as _csv, io
            from openpyxl import Workbook
            texto = contenido.decode('utf-8-sig', errors='replace')
            reader = _csv.reader(io.StringIO(texto))
            rows = list(reader)
            wb_tmp = Workbook(); ws_tmp = wb_tmp.active
            for _ in range(9): ws_tmp.append([])
            header_idx = 0
            for i, row in enumerate(rows):
                if row and 'Order Number' in str(row): header_idx = i; break
            if header_idx < len(rows):
                ws_tmp.append(['', ''] + rows[header_idx])
                for row in rows[header_idx+1:]:
                    if row: ws_tmp.append(['', ''] + row)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                wb_tmp.save(tmp.name); ruta_tmp = tmp.name
        except Exception as e:
            send(chat_id, f"❌ Error convirtiendo CSV: {e}"); return
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(contenido); ruta_tmp = tmp.name

    try:
        resultado = importar_c2c_inteligente(ruta_tmp, DB_PATH, str(chat_id))
        send(chat_id, formatear_resultado_inteligente(resultado))
    except Exception as e:
        import traceback
        send(chat_id, f"❌ Error: `{e}`\n```{traceback.format_exc()[-300:]}```")
    finally:
        try: os.remove(ruta_tmp)
        except: pass

# ══════════════════════════════════════════════════════════════════════
# LOOPS AUTOMÁTICOS v6.0
# ══════════════════════════════════════════════════════════════════════
def segundos_hasta_proximo_en_punto():
    """Calcula segundos hasta el próximo :00 o :30."""
    ahora = now_local()
    minuto = ahora.minute
    segundo = ahora.second
    if minuto < 30:
        faltan_min = 30 - minuto
    else:
        faltan_min = 60 - minuto
    return faltan_min * 60 - segundo

def loop_tasas():
    """Tasas sincronizadas al reloj: cada :00 y :30. Especiales a las 9AM y 1PM."""
    global ultimo_datos
    print("▶ Loop tasas sincronizado iniciado")

    # Primera espera hasta el próximo :00 o :30
    espera = segundos_hasta_proximo_en_punto()
    print(f"⏳ Esperando {espera}s para sincronizar tasas al reloj...")
    time.sleep(espera)

    while True:
        try:
            ahora = now_local()
            hora_actual = ahora.hour
            minuto_actual = ahora.minute
            es_especial = (hora_actual == 9 and minuto_actual < 5) or \
                          (hora_actual == 13 and minuto_actual < 5)

            print(f"\n⏰ Tasas — {ahora.strftime('%H:%M:%S')} {'★ ESPECIAL' if es_especial else ''}")
            datos = consultar_y_guardar(western_rate)
            ultimo_datos = datos
            send(TELEGRAM_CHAT_ID, construir_mensaje(datos, es_especial=es_especial))
        except Exception as e:
            print(f"Error tasas: {e}")

        # Esperar exactamente hasta el próximo :00 o :30
        time.sleep(segundos_hasta_proximo_en_punto())

def loop_mercado():
    """Monitorea precios reales BS y CLP cada 5 min. Guarda historial y envía alertas."""
    global ultimo_precio_bs_venta, ultimo_precio_clp
    print("▶ Loop mercado iniciado")
    time.sleep(30)  # Espera inicial

    while True:
        try:
            compras_bs, ventas_bs = get_top_anuncios_bs()
            clp_ads = get_top_anuncios_clp()
            cop_ads = get_top_anuncios_cop()

            # Guardar historial silenciosamente (siempre)
            if compras_bs or ventas_bs:
                guardar_precio_historico(compras_bs, ventas_bs, clp_ads, cop_ads)

            # Alerta BS si spread >= 10 y cambió >= 2 Bs
            if compras_bs and ventas_bs:
                spread = ventas_bs[0]
