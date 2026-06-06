"""
GSA CAMBIOS — BOT COMPLETO
Versión Railway: todo en un solo archivo.
"""

import os
import csv
import time
import sqlite3
import datetime
import requests
import threading

# ══════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH            = os.getenv("GSA_DB_PATH", "gsa_cambios.db")
CSV_EXPORT_PATH    = os.getenv("GSA_CSV_PATH", "csv_export")

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

SPREAD_SILENCIO  = 7
SPREAD_MODERADO  = 10
SPREAD_BUENO     = 15
SPREAD_PREMIUM   = 20

INTERVALO_TASAS_SEG  = 1800
INTERVALO_SPREAD_SEG = 300
INTERVALO_CSV_SEG    = 3600

TIPOS_OP = [
    "CLP→BS","BS→CLP","CLP→COP","COP→CLP","COP→BS","BS→COP",
    "CLP→USDT","USDT→CLP","BS→USDT","USDT→BS","USD→CLP","CLP→USD",
    "USD→BS","BS→USD","GIRO INT","USDC→USDT","USDT→USDC","USDT→USDT",
]
CORRESPONSALES = [
    "Bancolombia C1","Bancolombia C2",
    "Nequi C1","Nequi C2","Nequi C3","Efectivo Orlando",
]
CATEGORIAS_GASTOS = [
    "Fee Binance","Fee Airtm","Fee Bancario","Fee Copec Pay",
    "Encomienda/Delivery","Comunicaciones","Operativo","Otro",
]
NOMBRES_CUENTAS = {
    "BS_BANESCO":"Banesco","BS_MERCANTIL":"Mercantil",
    "CLP_COPEC_PAY":"Copec Pay","CLP_BANCOESTADO":"BancoEstado",
    "COP_EFECTIVO_ORLANDO":"Efectivo Orlando",
    "COP_BANCOLOMBIA_C1":"Bancolombia C1","COP_BANCOLOMBIA_C2":"Bancolombia C2",
    "COP_NEQUI_C1":"Nequi C1","COP_NEQUI_C2":"Nequi C2","COP_NEQUI_C3":"Nequi C3",
    "USD_EFECTIVO":"USD Efectivo","USDT_BINANCE":"Binance USDT","USDC_AIRTM":"Airtm USDC",
}

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
    conn.commit(); conn.close()
    print("✅ Base de datos lista")

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
        c.execute("INSERT OR IGNORE INTO saldos (cuenta,moneda,saldo) VALUES (?,?,0)",
                  (cuenta, moneda))
    conn.commit(); conn.close()

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

def guardar_tasa(datos):
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

def guardar_operacion(datos):
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

def actualizar_saldo(cuenta, delta):
    conn = get_conn()
    conn.execute("UPDATE saldos SET saldo=saldo+?,ultima_actualizacion=CURRENT_TIMESTAMP WHERE cuenta=?", (delta,cuenta))
    conn.commit(); conn.close()

def set_saldo(cuenta, saldo):
    conn = get_conn()
    conn.execute("INSERT INTO saldos (cuenta,moneda,saldo) VALUES (?,'',:s) ON CONFLICT(cuenta) DO UPDATE SET saldo=:s,ultima_actualizacion=CURRENT_TIMESTAMP",
                 {'cuenta':cuenta,'s':saldo})
    conn.commit(); conn.close()

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
    row = conn.execute("SELECT COUNT(*) as ops,COALESCE(SUM(usdt_equiv),0) as vol,COALESCE(SUM(usdt_equiv*diferencial),0) as gan FROM operaciones WHERE fecha=date('now') AND estado='Completada'").fetchone()
    gas = conn.execute("SELECT COALESCE(SUM(usdt_equiv),0) as t FROM gastos WHERE fecha=date('now')").fetchone()
    conn.close()
    return {'ops':row['ops'],'volumen':row['vol'],'ganancia_operativa':row['gan'],'gastos':gas['t'],'ganancia_neta':row['gan']-gas['t']}

def get_resultados_mes():
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as ops,COALESCE(SUM(usdt_equiv),0) as vol,COALESCE(SUM(usdt_equiv*diferencial),0) as gan FROM operaciones WHERE strftime('%Y-%m',fecha)=strftime('%Y-%m','now') AND estado='Completada'").fetchone()
    gas = conn.execute("SELECT COALESCE(SUM(usdt_equiv),0) as t FROM gastos WHERE strftime('%Y-%m',fecha)=strftime('%Y-%m','now')").fetchone()
    conn.close()
    return {'ops':row['ops'],'volumen':row['vol'],'ganancia_operativa':row['gan'],'gastos':gas['t'],'ganancia_neta':row['gan']-gas['t']}

def get_operaciones_hoy():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM operaciones WHERE fecha=date('now') ORDER BY hora").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_auditoria(limite=10):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM auditoria ORDER BY fecha_hora DESC LIMIT ?",(limite,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ══════════════════════════════════════════════════════════════════════
# APIS DE TASAS
# ══════════════════════════════════════════════════════════════════════
def get_binance_banco(banco):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type":"application/json"}
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

def get_binance_fiat(fiat):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type":"application/json"}
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
    ban_c,ban_v,ban_s = get_binance_banco("Banesco")
    mer_c,mer_v,mer_s = get_binance_banco("Mercantil")
    clp_c,clp_v = get_binance_fiat("CLP")
    cop_c,cop_v = get_binance_fiat("COP")
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
    guardar_tasa(datos)
    return datos

# ══════════════════════════════════════════════════════════════════════
# MENSAJES TELEGRAM
# ══════════════════════════════════════════════════════════════════════
def fmt(v, d=2): return f"{v:,.{d}f}" if v else "N/D"

def spread_emoji(s):
    if s>=SPREAD_PREMIUM: return "🚀"
    if s>=SPREAD_BUENO:   return "🟢"
    if s>=SPREAD_MODERADO:return "🟡"
    return "🔴"

def construir_mensaje(d):
    ahora = datetime.datetime.now().strftime("%d/%m/%Y — %I:%M %p")
    ban_s = d.get('ban_bs_spread',0) or 0
    mer_s = d.get('mer_bs_spread',0) or 0
    m  = f"📊 *RESUMEN DE TASAS*\n📅 {ahora}\n━━━━━━━━━━━━━━━━━━━━\n\n"
    m += f"🌎 *TASAS OFICIALES*\n\n"
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

def analizar_spread(mejor_banco, compra, venta, spread, ultimo):
    if not compra or not venta or spread < SPREAD_SILENCIO or spread == ultimo:
        return None, ultimo
    if spread >= SPREAD_PREMIUM: emoji,nivel = "🚀","PREMIUM"
    elif spread >= SPREAD_BUENO: emoji,nivel = "🟢","BUENO"
    else: emoji,nivel = "🟡","MODERADO"
    bs_rec = 100*(1-FEE_USDT_BS)*venta
    bs_pag = 100*compra
    gan_bs = bs_rec-bs_pag
    gan_u  = round(gan_bs/compra,4)
    msg  = f"{emoji} *SEÑAL P2P — {nivel}*\n\n🏦 Banco: *{mejor_banco}*\n\n"
    msg += f"Venta:  `{fmt(venta)} Bs`\nCompra: `{fmt(compra)} Bs`\nSpread: `{fmt(spread)} Bs`\n\n"
    msg += f"📊 *Por 100 USDT:*\n  Ganancia neta: `{fmt(gan_bs)} Bs`\n  En USDT: `~{fmt(gan_u,4)} USDT`"
    return msg, spread

# ══════════════════════════════════════════════════════════════════════
# IMPORTADOR BINANCE C2C
# ══════════════════════════════════════════════════════════════════════
def importar_c2c(ruta_archivo, usuario='importacion'):
    try:
        from openpyxl import load_workbook
        wb = load_workbook(ruta_archivo, data_only=True)
        ws = wb.active
    except Exception as e:
        return {'error': str(e)}

    conn = get_conn(); c = conn.cursor()
    importadas=omitidas=canceladas=errores=0
    res={'compras_ves':0,'ventas_ves':0,'compras_clp':0,'ventas_clp':0,
         'usdt_comprado_ves':0.0,'bs_pagado':0.0,'usdt_vendido_ves':0.0,
         'bs_recibido':0.0,'usdt_comprado_clp':0.0,'clp_pagado':0.0,'fee_total_usdt':0.0}

    for row in ws.iter_rows(min_row=11, values_only=True):
        if not row[2]: continue
        try:
            order_num  = str(row[2]); order_type = str(row[3])
            fiat       = str(row[5])
            total_fiat = float(str(row[6]).replace(',','')) if row[6] else 0
            precio     = float(str(row[7]).replace(',','')) if row[7] else 0
            cantidad   = float(str(row[8]).replace(',','')) if row[8] else 0
            maker_fee  = float(str(row[10]).replace(',','')) if row[10] else 0
            taker_fee  = float(str(row[11]).replace(',','')) if row[11] else 0
            contraparte= str(row[12]) if row[12] else ''
            status     = str(row[13]) if row[13] else ''
            created    = str(row[14]) if row[14] else ''
        except: errores+=1; continue

        if status != 'Completed': canceladas+=1; continue
        existe = c.execute("SELECT id FROM operaciones WHERE observaciones LIKE ?",
                           (f'%{order_num}%',)).fetchone()
        if existe: omitidas+=1; continue

        fee_usdt = maker_fee + taker_fee
        if fiat=='VES':
            if order_type=='Buy':
                tipo_op='BS→USDT'; mon_ent='BS'; mto_ent=total_fiat
                mon_sal='USDT'; mto_sal=cantidad-fee_usdt
                res['compras_ves']+=1; res['usdt_comprado_ves']+=cantidad; res['bs_pagado']+=total_fiat
            else:
                tipo_op='USDT→BS'; mon_ent='USDT'; mto_ent=cantidad
                mon_sal='BS'; mto_sal=total_fiat
                res['ventas_ves']+=1; res['usdt_vendido_ves']+=cantidad; res['bs_recibido']+=total_fiat
        elif fiat=='CLP':
            if order_type=='Buy':
                tipo_op='CLP→USDT'; mon_ent='CLP'; mto_ent=total_fiat
                mon_sal='USDT'; mto_sal=cantidad-fee_usdt
                res['compras_clp']+=1; res['usdt_comprado_clp']+=cantidad; res['clp_pagado']+=total_fiat
            else:
                tipo_op='USDT→CLP'; mon_ent='USDT'; mto_ent=cantidad
                mon_sal='CLP'; mto_sal=total_fiat; res['ventas_clp']+=1
        else: continue
        res['fee_total_usdt']+=fee_usdt

        try:
            fs = '20'+created if created.startswith('26-') else created
            dt = datetime.datetime.strptime(fs[:16],'%Y-%m-%d %H:%M')
            fecha=dt.strftime('%Y-%m-%d'); hora=dt.strftime('%H:%M')
        except:
            fecha=datetime.date.today().isoformat(); hora='00:00'

        try:
            c.execute("""INSERT INTO operaciones
                (fecha,hora,cliente,tipo_op,mon_entrada,monto_entrada,
                 mon_salida,monto_salida,tasa_cliente,tasa_referencia,
                 usdt_equiv,diferencial,metodo,estado,observaciones,usuario_telegram)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (fecha,hora,f"Binance P2P ({contraparte})",tipo_op,
                 mon_ent,mto_ent,mon_sal,mto_sal,precio,precio,
                 cantidad,0,'Binance P2P','Completada',
                 f"Orden Binance #{order_num} | Fee: {fee_usdt:.4f} USDT",usuario))
            importadas+=1
        except: errores+=1

    conn.commit(); conn.close()
    cpp = res['bs_pagado']/res['usdt_comprado_ves'] if res['usdt_comprado_ves'] else 0
    pv  = res['bs_recibido']/res['usdt_vendido_ves'] if res['usdt_vendido_ves'] else 0
    cpp_clp = res['clp_pagado']/res['usdt_comprado_clp'] if res['usdt_comprado_clp'] else 0
    return {'importadas':importadas,'omitidas':omitidas,'canceladas':canceladas,
            'errores':errores,'resumen':res,'cpp_ves':round(cpp,4),
            'precio_venta':round(pv,4),'spread':round(pv-cpp,4),'cpp_clp':round(cpp_clp,4)}

def formatear_importacion(resultado):
    if 'error' in resultado: return f"❌ Error: {resultado['error']}"
    r=resultado['resumen']
    m  = f"✅ *IMPORTACIÓN BINANCE C2C*\n\n"
    m += f"Importadas: `{resultado['importadas']}` | Omitidas: `{resultado['omitidas']}` | Canceladas: `{resultado['canceladas']}`\n\n"
    if r['compras_ves']>0:
        m += f"🇻🇪 *Compras BS→USDT ({r['compras_ves']} órdenes)*\n"
        m += f"  USDT: `{r['usdt_comprado_ves']:.4f}` | BS: `{r['bs_pagado']:,.2f}` | CPP: `{resultado['cpp_ves']:.4f}`\n\n"
    if r['ventas_ves']>0:
        m += f"🇻🇪 *Ventas USDT→BS ({r['ventas_ves']} órdenes)*\n"
        m += f"  USDT: `{r['usdt_vendido_ves']:.4f}` | BS: `{r['bs_recibido']:,.2f}` | Precio: `{resultado['precio_venta']:.4f}`\n\n"
    if r['compras_clp']>0:
        m += f"🇨🇱 *Compras CLP→USDT ({r['compras_clp']} órdenes)*\n"
        m += f"  USDT: `{r['usdt_comprado_clp']:.4f}` | CLP: `{r['clp_pagado']:,.2f}` | Precio: `{resultado['cpp_clp']:.4f}`\n\n"
    m += f"💸 Fees totales: `{r['fee_total_usdt']:.4f} USDT`"
    return m

# ══════════════════════════════════════════════════════════════════════
# CONVERSACIÓN /operacion
# ══════════════════════════════════════════════════════════════════════
conversaciones = {}

def iniciar_operacion(chat_id):
    conversaciones[chat_id] = {'paso':0,'datos':{
        'fecha':str(datetime.date.today()),
        'hora':datetime.datetime.now().strftime("%H:%M"),
        'usuario_telegram':str(chat_id),'estado':'Completada',
        'traslado_bs':0,'encomienda_cop':0,'cxc_pendiente':0,'cxp_pendiente':0,
        'repartidor':'Cristofer Ruiz',
    }}
    tipos = "\n".join([f"  `{t}`" for t in TIPOS_OP])
    return f"💱 *NUEVA OPERACIÓN*\n\n¿Tipo de operación?\n\n{tipos}\n\n_/cancelar para salir_"

def procesar_conv(chat_id, texto):
    if chat_id not in conversaciones:
        return "No hay operación activa. Usa /operacion para iniciar."
    conv=conversaciones[chat_id]; paso=conv['paso']; datos=conv['datos']
    if texto.lower() in ('/cancelar','cancelar'):
        del conversaciones[chat_id]; return "❌ Operación cancelada."

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
            t=get_ultima_tasa()
            tasa_sug=_tasa_sug(datos['tipo_op'],t)
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
                val=float(texto.replace(',','.'))
                datos['tasa_cliente']=val
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
        return f"💳 ¿El cliente quedó debiendo? (*no*, *si*, o el monto)"

    elif paso==61:
        try:
            monto=float(texto.replace(',','.'))
            if monto>0:
                if monto>10000: datos['encomienda_cop']=monto
                else: datos['traslado_bs']=monto
            conv['paso']=7
            return f"💳 ¿El cliente quedó debiendo? (*no*, *si*, o el monto)"
        except: return "⚠️ Ingresa un número o *0*"

    elif paso==7:
        if texto.lower() in ('no','n','0'): datos['cxc_pendiente']=0
        elif texto.lower() in ('si','sí','s'):
            conv['paso']=71
            return f"¿Cuánto {datos.get('mon_entrada','?')} debe el cliente?"
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
            m  = f"✅ *Op #{op_id} registrada*\n"
            m += f"Cliente: `{datos['cliente']}`\nTipo: `{datos['tipo_op']}`\n"
            m += f"USDT: `{datos.get('usdt_equiv',0):.4f}`\n"
            if datos.get('cxc_pendiente',0)>0: m+=f"⚠️ CXC: `{datos['cxc_pendiente']:,.2f} {datos['mon_entrada']}`\n"
            m += "_Saldos actualizados_"; return m
        del conversaciones[chat_id]; return "❌ Operación cancelada."
    return "⚠️ Algo salió mal. Usa /operacion para reiniciar."

def _resumen(datos):
    m  = f"📋 *CONFIRMAR*\n━━━━━━━━━━━━━━━━━━━━\n"
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
# MENSAJES DE SALDOS Y DASHBOARD
# ══════════════════════════════════════════════════════════════════════
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
    ahora=datetime.datetime.now().strftime("%d/%m %I:%M %p")
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
    ahora=datetime.datetime.now().strftime("%d/%m/%Y %I:%M %p")
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
    m+="_/saldo para ver todas las cuentas_"
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

# ══════════════════════════════════════════════════════════════════════
# EXPORTAR CSV PARA EXCEL
# ══════════════════════════════════════════════════════════════════════
def exportar_csv():
    os.makedirs(CSV_EXPORT_PATH, exist_ok=True)
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    for tabla in ['tasas','operaciones','saldos','clientes','gastos','tesoreria','cuentas_pendientes']:
        try:
            rows=conn.execute(f"SELECT * FROM {tabla}").fetchall()
            if not rows: continue
            ruta=os.path.join(CSV_EXPORT_PATH,f"{tabla}.csv")
            with open(ruta,'w',newline='',encoding='utf-8-sig') as f:
                w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader()
                w.writerows([dict(r) for r in rows])
        except: pass
    conn.close()
    print(f"✅ CSV exportados — {datetime.datetime.now().strftime('%H:%M:%S')}")

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

ultimo_offset=0; western_rate=None; ultimo_spread=0; ultimo_datos={}
esperando_importar={}

def procesar(chat_id, texto):
    global western_rate, ultimo_datos

    # Conversación activa de operación
    if hay_conv_activa(chat_id) and not texto.startswith('/'):
        send(chat_id, procesar_conv(chat_id, texto)); return

    # Esperando nombre de archivo para importar
    if chat_id in esperando_importar and not texto.startswith('/'):
        archivo=texto.strip()
        ruta=os.path.join(os.path.dirname(DB_PATH), archivo)
        if not os.path.exists(ruta):
            ruta=os.path.join(CSV_EXPORT_PATH,'..', archivo)
            ruta=os.path.abspath(ruta)
        send(chat_id, f"⏳ Procesando `{archivo}`...")
        resultado=importar_c2c(ruta, str(chat_id))
        send(chat_id, formatear_importacion(resultado))
        del esperando_importar[chat_id]; return

    partes=texto.split(); cmd=partes[0].lower() if partes else ''

    if cmd=='/tasas':
        global western_rate
        send(chat_id,"⏳ Consultando tasas...")
        datos=consultar_y_guardar(western_rate); ultimo_datos=datos
        send(chat_id, construir_mensaje(datos))

    elif cmd=='/western':
        if len(partes)>=2:
            try: western_rate=float(partes[1].replace(',','.')); send(chat_id,f"✅ Western: `{western_rate}`")
            except: send(chat_id,"Uso: /western 0.0042")
        else: send(chat_id,"Uso: `/western 0.0042`")

    elif cmd=='/limites':
        t=ultimo_datos or {}
        m=f"📐 *LÍMITES*\nCLP/BS: `{t.get('limite_clp_bs','N/D')}`\nCLP/COP: `{t.get('limite_clp_cop','N/D')}`"
        send(chat_id,m)

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

    elif cmd=='/saldo': send(chat_id, msg_saldos())
    elif cmd=='/caja': send(chat_id, msg_saldos())
    elif cmd=='/posicion': send(chat_id, msg_saldos())
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

    elif cmd=='/importar':
        esperando_importar[chat_id]=True
        send(chat_id,
             "📂 *IMPORTAR BINANCE C2C*\n\n"
             "1. Descarga el historial C2C desde Binance\n"
             "2. Súbelo a Railway como variable o ponlo accesible\n\n"
             "Escribe el nombre del archivo .xlsx:\n"
             "_/cancelar para salir_")

    elif cmd=='/sync':
        send(chat_id,"⏳ Exportando CSV...")
        exportar_csv(); send(chat_id,"✅ CSV exportados para Excel.")

    elif cmd=='/auditoria':
        regs=get_auditoria(10)
        if not regs: send(chat_id,"Sin auditoría."); return
        m="🔍 *ÚLTIMOS CAMBIOS*\n\n"
        for r in regs: m+=f"`{r['fecha_hora'][:16]}` {r['accion']} — {r['modulo']}\n"
        send(chat_id,m)

    elif cmd in ('/ayuda','/start','/help'):
        send(chat_id,"""🤖 *GSA CAMBIOS — COMANDOS*

*📊 TASAS*
/tasas | /western TASA | /limites

*💱 OPERACIONES*
/operacion | /operaciones | /ultima

*💰 SALDOS*
/saldo | /caja | /posicion

*📈 RESULTADOS*
/dashboard | /resultado | /ganancia

*📋 PENDIENTES*
/cxc | /cxp | /cobrado ID | /pagado ID

*⚙️ SISTEMA*
/importar | /sync | /auditoria | /ayuda""")

    elif hay_conv_activa(chat_id):
        send(chat_id, procesar_conv(chat_id, texto))

# ══════════════════════════════════════════════════════════════════════
# LOOPS AUTOMÁTICOS
# ══════════════════════════════════════════════════════════════════════
def loop_tasas():
    global ultimo_datos, ultimo_spread
    print("▶ Loop tasas iniciado")
    while True:
        try:
            print(f"\n⏰ Tasas — {datetime.datetime.now().strftime('%H:%M:%S')}")
            datos=consultar_y_guardar(western_rate)
            ultimo_datos=datos
            send(TELEGRAM_CHAT_ID, construir_mensaje(datos))
        except Exception as e: print(f"Error tasas: {e}")
        time.sleep(INTERVALO_TASAS_SEG)

def loop_spread():
    global ultimo_spread
    print("▶ Loop spread iniciado")
    while True:
        try:
            d=ultimo_datos
            if d:
                ban_s=d.get('ban_bs_spread',0) or 0; mer_s=d.get('mer_bs_spread',0) or 0
                if mer_s>ban_s: banco,c,v,s="Mercantil",d.get('mer_bs_compra'),d.get('mer_bs_venta'),mer_s
                else: banco,c,v,s="Banesco",d.get('ban_bs_compra'),d.get('ban_bs_venta'),ban_s
                alerta,nuevo=analizar_spread(banco,c,v,s,ultimo_spread)
                if alerta: send(TELEGRAM_CHAT_ID,alerta); ultimo_spread=nuevo
        except Exception as e: print(f"Error spread: {e}")
        time.sleep(INTERVALO_SPREAD_SEG)

def loop_csv():
    print("▶ Loop CSV iniciado")
    while True:
        try: exportar_csv()
        except Exception as e: print(f"Error CSV: {e}")
        time.sleep(INTERVALO_CSV_SEG)

# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    global ultimo_offset
    print("="*50)
    print("   GSA CAMBIOS — BOT INICIANDO")
    print("="*50)
    init_db(); init_saldos()
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN no configurado"); return

    threading.Thread(target=loop_tasas, daemon=True).start()
    threading.Thread(target=loop_spread, daemon=True).start()
    threading.Thread(target=loop_csv, daemon=True).start()

    send(TELEGRAM_CHAT_ID,"✅ *GSA Cambios Bot iniciado*\n\nUsa /ayuda para ver los comandos.")
    print("\n✅ Bot corriendo...\n")

    while True:
        try:
            updates=get_updates(ultimo_offset)
            for update in updates:
                ultimo_offset=update["update_id"]+1
                if "message" in update:
                    msg=update["message"]
                    chat_id=str(msg["chat"]["id"])
                    texto=msg.get("text","")
                    if texto: procesar(chat_id, texto)
        except Exception as e: print(f"Error main: {e}"); time.sleep(5)

if __name__=="__main__":
    main()
