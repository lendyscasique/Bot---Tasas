"""GSA Cambios — Motor de Pricing V1 compatible con Bot V1.0.5.

Conserva íntegramente la API legacy usada por bot.py y añade el nuevo
motor V1 para las 18 operaciones, guardrails y soporte maker/taker.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Tuple

# Política comercial centralizada
MARGEN_RECOMENDADO = 0.07
MARGEN_PREFERENCIAL = 0.05
MARGEN_CAPTACION = 0.03
UTILIDAD_MINIMA_COP = 10_000.0

COMISION_REFERIDO = 0.03
COMISION_CORRESPONSAL = 0.05
COMISION_COMPRA_COP = 0.003
FEE_CLP_USDT = 0.002
FEE_USDT_BS = 0.0025
EQUILIBRIO_TOL_COP = 1.0


def _positivo(valor: float, nombre: str) -> float:
    v = float(valor)
    if v < 0:
        raise ValueError(f"{nombre} no puede ser negativo")
    return v


def producir_bs_desde_clp(
    monto_clp: float,
    tasa_clp_usdt: float,
    tasa_usdt_bs: float,
    fee_clp_usdt: float = FEE_CLP_USDT,
    fee_usdt_bs: float = FEE_USDT_BS,
) -> Dict[str, float]:
    """Proyecta el ciclo CLP→USDT→BS con fees explícitos.

    tasa_clp_usdt: CLP por 1 USDT pagado al comprar USDT.
    tasa_usdt_bs: BS recibidos por 1 USDT al vender USDT.
    """
    monto_clp = _positivo(monto_clp, "monto_clp")
    tasa_clp_usdt = float(tasa_clp_usdt)
    tasa_usdt_bs = float(tasa_usdt_bs)
    if monto_clp <= 0 or tasa_clp_usdt <= 0 or tasa_usdt_bs <= 0:
        raise ValueError("monto y tasas deben ser mayores a cero")

    usdt_brutos = monto_clp / tasa_clp_usdt
    fee_usdt_compra = usdt_brutos * fee_clp_usdt
    usdt_netos = usdt_brutos - fee_usdt_compra
    bs_brutos = usdt_netos * tasa_usdt_bs
    fee_bs_venta = bs_brutos * fee_usdt_bs
    bs_netos = bs_brutos - fee_bs_venta

    return {
        "monto_clp": round(monto_clp, 2),
        "tasa_clp_usdt": round(tasa_clp_usdt, 6),
        "usdt_brutos": round(usdt_brutos, 8),
        "fee_usdt_compra": round(fee_usdt_compra, 8),
        "usdt_netos": round(usdt_netos, 8),
        "tasa_usdt_bs": round(tasa_usdt_bs, 6),
        "bs_brutos": round(bs_brutos, 8),
        "fee_bs_venta": round(fee_bs_venta, 8),
        "bs_netos": round(bs_netos, 8),
    }


def calcular_capacidad_cop(
    bs_disponibles: float,
    tasa_bs_cop: float,
    comision_compra_cop: float = COMISION_COMPRA_COP,
) -> float:
    """COP económicos producibles con BS atribuibles a la operación.

    La comisión BS→COP se paga adicional al principal desde la misma bolsa
    económica atribuible, por eso se divide entre (1 + comisión).
    """
    bs = _positivo(bs_disponibles, "bs_disponibles")
    tasa = float(tasa_bs_cop)
    if bs <= 0 or tasa <= 0:
        raise ValueError("bs_disponibles y tasa_bs_cop deben ser mayores a cero")
    return round((bs * tasa) / (1.0 + comision_compra_cop), 8)


def calcular_costos_operacion(
    cop_cliente: float,
    referido: bool = False,
    delivery_cop: float = 0.0,
    avance_corresponsal_cop: float = 0.0,
    comision_referido: float = COMISION_REFERIDO,
    comision_corresponsal: float = COMISION_CORRESPONSAL,
) -> Dict[str, float]:
    cop_cliente = _positivo(cop_cliente, "cop_cliente")
    delivery_cop = _positivo(delivery_cop, "delivery_cop")
    avance = _positivo(avance_corresponsal_cop, "avance_corresponsal_cop")

    costo_referido = cop_cliente * comision_referido if referido else 0.0
    costo_corresponsal = avance * comision_corresponsal
    total = costo_referido + delivery_cop + costo_corresponsal
    return {
        "comision_referido_cop": round(costo_referido, 8),
        "delivery_cop": round(delivery_cop, 8),
        "avance_corresponsal_cop": round(avance, 8),
        "comision_corresponsal_cop": round(costo_corresponsal, 8),
        "total_costos_cop": round(total, 8),
    }


def clasificar_rentabilidad(
    utilidad_cop: float,
    rentabilidad: float,
    utilidad_minima_cop: float = UTILIDAD_MINIMA_COP,
) -> str:
    if utilidad_cop < -EQUILIBRIO_TOL_COP:
        return "PERDIDA"
    if abs(utilidad_cop) <= EQUILIBRIO_TOL_COP:
        return "EQUILIBRIO"
    if utilidad_cop < utilidad_minima_cop or rentabilidad < MARGEN_CAPTACION:
        return "FUERA_POLITICA"
    if rentabilidad < MARGEN_PREFERENCIAL:
        return "CAPTACION"
    if rentabilidad < MARGEN_RECOMENDADO:
        return "PREFERENCIAL"
    return "RECOMENDADA"


def evaluar_tasa_clp_cop(
    monto_clp: float,
    tasa_cliente: float,
    cop_potenciales: float,
    referido: bool = False,
    delivery_cop: float = 0.0,
    avance_corresponsal_cop: float = 0.0,
    utilidad_minima_cop: float = UTILIDAD_MINIMA_COP,
) -> Dict[str, Any]:
    monto_clp = _positivo(monto_clp, "monto_clp")
    tasa_cliente = float(tasa_cliente)
    cop_potenciales = _positivo(cop_potenciales, "cop_potenciales")
    if monto_clp <= 0 or tasa_cliente <= 0:
        raise ValueError("monto_clp y tasa_cliente deben ser mayores a cero")

    cop_cliente = monto_clp * tasa_cliente
    costos = calcular_costos_operacion(
        cop_cliente,
        referido=referido,
        delivery_cop=delivery_cop,
        avance_corresponsal_cop=avance_corresponsal_cop,
    )
    utilidad = cop_potenciales - cop_cliente - costos["total_costos_cop"]
    rentabilidad = utilidad / cop_cliente if cop_cliente else 0.0
    clasificacion = clasificar_rentabilidad(utilidad, rentabilidad, utilidad_minima_cop)

    return {
        "monto_clp": round(monto_clp, 2),
        "tasa_cliente": round(tasa_cliente, 6),
        "cop_cliente": round(cop_cliente, 8),
        "cop_potenciales": round(cop_potenciales, 8),
        **costos,
        "utilidad_cop": round(utilidad, 8),
        "rentabilidad": round(rentabilidad, 10),
        "rentabilidad_pct": round(rentabilidad * 100.0, 4),
        "clasificacion": clasificacion,
        "cumple_utilidad_minima": utilidad >= utilidad_minima_cop,
    }


def calcular_tasa_para_margen(
    monto_clp: float,
    cop_potenciales: float,
    margen_objetivo: float,
    referido: bool = False,
    delivery_cop: float = 0.0,
    avance_corresponsal_cop: float = 0.0,
) -> Dict[str, float]:
    """Despeja la tasa máxima al cliente que conserva el margen objetivo."""
    monto_clp = _positivo(monto_clp, "monto_clp")
    cop_potenciales = _positivo(cop_potenciales, "cop_potenciales")
    delivery = _positivo(delivery_cop, "delivery_cop")
    avance = _positivo(avance_corresponsal_cop, "avance_corresponsal_cop")
    if monto_clp <= 0:
        raise ValueError("monto_clp debe ser mayor a cero")

    r = COMISION_REFERIDO if referido else 0.0
    costo_corr = avance * COMISION_CORRESPONSAL
    disponible_para_cliente_y_porcentajes = cop_potenciales - delivery - costo_corr
    divisor = 1.0 + r + float(margen_objetivo)
    cop_cliente = disponible_para_cliente_y_porcentajes / divisor
    tasa = cop_cliente / monto_clp
    utilidad_objetivo = cop_cliente * float(margen_objetivo)

    return {
        "margen_objetivo": float(margen_objetivo),
        "tasa": round(tasa, 6),
        "cop_cliente": round(cop_cliente, 8),
        "utilidad_objetivo_cop": round(utilidad_objetivo, 8),
    }


def calcular_niveles_tasa(
    monto_clp: float,
    cop_potenciales: float,
    referido: bool = False,
    delivery_cop: float = 0.0,
    avance_corresponsal_cop: float = 0.0,
    utilidad_minima_cop: float = UTILIDAD_MINIMA_COP,
) -> Dict[str, Dict[str, Any]]:
    niveles = {
        "recomendada": MARGEN_RECOMENDADO,
        "preferencial": MARGEN_PREFERENCIAL,
        "captacion": MARGEN_CAPTACION,
        "equilibrio": 0.0,
    }
    salida: Dict[str, Dict[str, Any]] = {}
    for nombre, margen in niveles.items():
        base = calcular_tasa_para_margen(
            monto_clp,
            cop_potenciales,
            margen,
            referido=referido,
            delivery_cop=delivery_cop,
            avance_corresponsal_cop=avance_corresponsal_cop,
        )
        ev = evaluar_tasa_clp_cop(
            monto_clp,
            base["tasa"],
            cop_potenciales,
            referido=referido,
            delivery_cop=delivery_cop,
            avance_corresponsal_cop=avance_corresponsal_cop,
            utilidad_minima_cop=utilidad_minima_cop,
        )
        salida[nombre] = {**base, **{
            "utilidad_cop": ev["utilidad_cop"],
            "rentabilidad_pct": ev["rentabilidad_pct"],
            "clasificacion": ev["clasificacion"],
            "cumple_utilidad_minima": ev["cumple_utilidad_minima"],
        }}
    return salida


def calcular_bs_cop_requerida(
    bs_disponibles: float,
    monto_clp: float,
    tasa_cliente: float,
    margen_objetivo: float,
    referido: bool = False,
    delivery_cop: float = 0.0,
    avance_corresponsal_cop: float = 0.0,
    comision_compra_cop: float = COMISION_COMPRA_COP,
) -> float:
    """Tasa nominal BS→COP necesaria para sostener una tasa al cliente."""
    bs = _positivo(bs_disponibles, "bs_disponibles")
    monto_clp = _positivo(monto_clp, "monto_clp")
    tasa_cliente = float(tasa_cliente)
    if bs <= 0 or monto_clp <= 0 or tasa_cliente <= 0:
        raise ValueError("bs, monto_clp y tasa_cliente deben ser mayores a cero")

    cop_cliente = monto_clp * tasa_cliente
    r = COMISION_REFERIDO if referido else 0.0
    delivery = _positivo(delivery_cop, "delivery_cop")
    costo_corr = _positivo(avance_corresponsal_cop, "avance_corresponsal_cop") * COMISION_CORRESPONSAL
    cop_requeridos = cop_cliente * (1.0 + r + float(margen_objetivo)) + delivery + costo_corr
    tasa_requerida = cop_requeridos * (1.0 + comision_compra_cop) / bs
    return round(tasa_requerida, 6)


def comparar_western(monto_clp: float, tasa_gsa: float, western: Optional[float]) -> Optional[Dict[str, float]]:
    if western is None or float(western) <= 0:
        return None
    monto = _positivo(monto_clp, "monto_clp")
    tasa_gsa = float(tasa_gsa)
    western = float(western)
    cop_gsa = monto * tasa_gsa
    cop_western = monto * western
    return {
        "western": round(western, 6),
        "tasa_gsa": round(tasa_gsa, 6),
        "cop_western": round(cop_western, 8),
        "cop_gsa": round(cop_gsa, 8),
        "brecha_tasa": round(western - tasa_gsa, 6),
        "brecha_cop": round(cop_western - cop_gsa, 8),
    }


# ══════════════════════════════════════════════════════════════════════
# MOTOR V1 — 18 OPERACIONES (API NUEVA)
# ══════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────
# POLÍTICAS V1
# ─────────────────────────────────────────────────────────────────────
MARGEN_CLP_BS_RECOMENDADO = 0.07
MARGEN_CLP_BS_AUTO = 0.05
MARGEN_CLP_BS_CAPTACION = 0.03

MARGEN_BS_CLP_PROVISIONAL = 0.05
MARGEN_COP_BS_PROVISIONAL = 0.05
MARGEN_BS_COP_PROVISIONAL = 0.05

MARGEN_COP_CLP = 0.05
SPREAD_USD_CLP = 50.0
SPREAD_CLP_USDT = 20.0
SPREAD_USDT_CLP = 20.0
COMISION_GSA_WESTERN = 0.05
SPREAD_COMPRA_USD_BS = 30.0
ALPHA_USD_COP = 0.50
SPREAD_USDT_COP = 0.01
MARGEN_USDT_USD = 0.025
FEE_BANESCO_OTRO_BANCO = 0.003

CLP_COP_TRAMOS = (
    (25_000.0, 3.00),
    (50_000.0, 3.05),
    (150_000.0, 3.10),
    (float("inf"), 3.15),
)

ESTADO_RENTABLE = "RENTABLE"
ESTADO_MARGEN_COMPRIMIDO = "MARGEN_COMPRIMIDO"
ESTADO_CAPTACION = "CAPTACION"
ESTADO_ESTRATEGICA = "ESTRATEGICA"
ESTADO_NO_RECOMENDADO = "NO_RECOMENDADO"
ESTADO_BLOQUEADO = "BLOQUEADO"

POLICY_DEFINITIVA = "DEFINITIVA"
POLICY_PROVISIONAL = "PROVISIONAL"

ALERTA_MARGEN_COMPRIMIDO = "ALERTA_MARGEN_COMPRIMIDO"
ALERTA_CAPTACION = "ALERTA_CAPTACION"
ALERTA_POLITICA_PROVISIONAL = "ALERTA_POLITICA_PROVISIONAL"
ALERTA_BANESCO_003 = "ALERTA_BANESCO_003"
ALERTA_MAKER_NO_DISPONIBLE = "ALERTA_MAKER_NO_DISPONIBLE"
ALERTA_TAKER_NO_DISPONIBLE = "ALERTA_TAKER_NO_DISPONIBLE"
ALERTA_COSTO_REPOSICION = "ALERTA_COSTO_REPOSICION"
ALERTA_INVENTARIO = "ALERTA_INVENTARIO"
ALERTA_WESTERN_BAJO_UMBRAL = "ALERTA_WESTERN_BAJO_UMBRAL"
ALERTA_MERCADO_FISICO_INVALIDO = "ALERTA_MERCADO_FISICO_INVALIDO"
ALERTA_DATO_INSUFICIENTE = "ALERTA_DATO_INSUFICIENTE"
ALERTA_LIQUIDEZ_INSUFICIENTE = "ALERTA_LIQUIDEZ_INSUFICIENTE"
ALERTA_OPERACION_NO_RENTABLE = "ALERTA_OPERACION_NO_RENTABLE"
ALERTA_INPUT_INVALIDO = "ALERTA_INPUT_INVALIDO"
ALERTA_SPREAD_PROVISIONAL_1 = "ALERTA_SPREAD_PROVISIONAL_1"


def _num(v: Any, nombre: str, *, allow_zero: bool = False) -> float:
    try:
        x = float(v)
    except Exception as exc:
        raise ValueError(f"{nombre} inválido") from exc
    if x < 0 or (x == 0 and not allow_zero):
        raise ValueError(f"{nombre} debe ser {'no negativo' if allow_zero else 'mayor a cero'}")
    return x


def _resultado(
    operacion: str,
    monto_origen: float,
    moneda_origen: str,
    moneda_destino: str,
    *,
    referencia_mercado: Optional[float] = None,
    ruta_economica: str = "",
    modo_ejecucion: str = "",
    capacidad_bruta: Optional[float] = None,
    costos_totales: float = 0.0,
    capacidad_neta: Optional[float] = None,
    tasa_comercial: Optional[float] = None,
    monto_cliente: Optional[float] = None,
    utilidad_esperada: Optional[float] = None,
    margen_esperado: Optional[float] = None,
    estado: str = ESTADO_RENTABLE,
    policy_status: str = POLICY_DEFINITIVA,
    alertas: Optional[list[str]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    r = {
        "operacion": operacion,
        "monto_origen": monto_origen,
        "moneda_origen": moneda_origen,
        "moneda_destino": moneda_destino,
        "referencia_mercado": referencia_mercado,
        "ruta_economica": ruta_economica,
        "modo_ejecucion": modo_ejecucion,
        "capacidad_bruta": capacidad_bruta,
        "costos_totales": costos_totales,
        "capacidad_neta": capacidad_neta,
        "tasa_comercial": tasa_comercial,
        "monto_cliente": monto_cliente,
        "utilidad_esperada": utilidad_esperada,
        "margen_esperado": margen_esperado,
        "estado": estado,
        "policy_status": policy_status,
        "alertas": alertas or [],
    }
    r.update(extra)
    return r


def evaluar_ejecucion_p2p(
    direccion: str,
    *,
    precio_maker: Optional[float] = None,
    fee_maker: float = 0.0,
    maker_disponible: bool = False,
    precio_taker: Optional[float] = None,
    fee_taker: float = 0.0,
    taker_disponible: bool = False,
    modo: str = "AUTO",
) -> Dict[str, Any]:
    direccion = str(direccion).upper()
    modo = str(modo).upper()
    if direccion not in {"COMPRA", "VENTA"}:
        raise ValueError("direccion debe ser COMPRA o VENTA")
    if modo not in {"AUTO", "MAKER", "TAKER"}:
        raise ValueError("modo debe ser AUTO, MAKER o TAKER")

    opciones = {}
    alertas = []

    if maker_disponible:
        if precio_maker is None:
            raise ValueError("precio_maker requerido")
        p = _num(precio_maker, "precio_maker")
        f = _num(fee_maker, "fee_maker", allow_zero=True)
        opciones["MAKER"] = p + f if direccion == "COMPRA" else p - f
    else:
        alertas.append(ALERTA_MAKER_NO_DISPONIBLE)

    if taker_disponible:
        if precio_taker is None:
            raise ValueError("precio_taker requerido")
        p = _num(precio_taker, "precio_taker")
        f = _num(fee_taker, "fee_taker", allow_zero=True)
        opciones["TAKER"] = p + f if direccion == "COMPRA" else p - f
    else:
        alertas.append(ALERTA_TAKER_NO_DISPONIBLE)

    if not opciones:
        return {
            "ok": False,
            "modo": None,
            "valor_neto": None,
            "alertas": alertas + [ALERTA_LIQUIDEZ_INSUFICIENTE],
        }

    if modo != "AUTO":
        if modo not in opciones:
            return {
                "ok": False,
                "modo": None,
                "valor_neto": None,
                "alertas": alertas + [ALERTA_LIQUIDEZ_INSUFICIENTE],
            }
        elegido = modo
    elif direccion == "COMPRA":
        elegido = min(opciones, key=opciones.get)
    else:
        elegido = max(opciones, key=opciones.get)

    return {
        "ok": True,
        "modo": elegido,
        "valor_neto": opciones[elegido],
        "alternativas": opciones,
        "alertas": alertas,
    }


def calcular_fee_pago_bs(monto_bs: float, cuenta_origen: str, mismo_banco: bool) -> float:
    monto = _num(monto_bs, "monto_bs", allow_zero=True)
    if str(cuenta_origen).upper() == "BANESCO" and not mismo_banco:
        return monto * FEE_BANESCO_OTRO_BANCO
    return 0.0


def evaluar_rentabilidad(
    capacidad_neta: float,
    monto_cliente: float,
    *,
    costos_pendientes: float = 0.0,
    margen_objetivo: Optional[float] = None,
    permitir_captacion: bool = False,
) -> Dict[str, Any]:
    c = _num(capacidad_neta, "capacidad_neta", allow_zero=True)
    p = _num(monto_cliente, "monto_cliente")
    f = _num(costos_pendientes, "costos_pendientes", allow_zero=True)
    u = c - p - f
    r = u / p
    alertas = []
    if u <= 0:
        return {"utilidad": u, "margen": r, "estado": ESTADO_BLOQUEADO,
                "alertas": [ALERTA_OPERACION_NO_RENTABLE]}
    if margen_objetivo is None or r >= margen_objetivo:
        return {"utilidad": u, "margen": r, "estado": ESTADO_RENTABLE, "alertas": []}
    if permitir_captacion:
        return {"utilidad": u, "margen": r, "estado": ESTADO_CAPTACION,
                "alertas": [ALERTA_CAPTACION, ALERTA_MARGEN_COMPRIMIDO]}
    return {"utilidad": u, "margen": r, "estado": ESTADO_MARGEN_COMPRIMIDO,
            "alertas": [ALERTA_MARGEN_COMPRIMIDO]}


def _margen_por_selector(selector: str) -> float:
    s = str(selector).upper()
    return {
        "RECOMENDADO": MARGEN_CLP_BS_RECOMENDADO,
        "AUTO": MARGEN_CLP_BS_AUTO,
        "CAPTACION": MARGEN_CLP_BS_CAPTACION,
        "7": MARGEN_CLP_BS_RECOMENDADO,
        "5": MARGEN_CLP_BS_AUTO,
        "3": MARGEN_CLP_BS_CAPTACION,
    }.get(s, MARGEN_CLP_BS_AUTO)


# 1
def cotizar_clp_bs(monto_clp: float, capacidad_bs: float, *, tasa_cliente: Optional[float] = None,
                   margen: str = "AUTO", costos_pendientes: float = 0.0) -> Dict[str, Any]:
    m = _num(monto_clp, "monto_clp")
    c = _num(capacidad_bs, "capacidad_bs")
    obj = _margen_por_selector(margen)
    tasa = float(tasa_cliente) if tasa_cliente is not None else (c - costos_pendientes) / (1 + obj) / m
    p = m * tasa
    ev = evaluar_rentabilidad(c, p, costos_pendientes=costos_pendientes,
                              margen_objetivo=obj, permitir_captacion=(str(margen).upper()=="CAPTACION"))
    return _resultado("CLP_BS", m, "CLP", "BS", ruta_economica="CLP>USDT>BS",
                      capacidad_bruta=c, capacidad_neta=c, costos_totales=costos_pendientes,
                      tasa_comercial=tasa, monto_cliente=p,
                      utilidad_esperada=ev["utilidad"], margen_esperado=ev["margen"],
                      estado=ev["estado"], alertas=ev["alertas"])


# 2
def cotizar_bs_clp(monto_bs: float, capacidad_clp: float,
                   *, margen: float = MARGEN_BS_CLP_PROVISIONAL,
                   tasa_bs_por_clp: Optional[float] = None) -> Dict[str, Any]:
    m = _num(monto_bs, "monto_bs")
    c = _num(capacidad_clp, "capacidad_clp")

    # Compatibilidad legacy.
    if tasa_bs_por_clp is None:
        p = c / (1 + margen)
        ev = evaluar_rentabilidad(c, p, margen_objetivo=margen)
        return _resultado("BS_CLP", m, "BS", "CLP", ruta_economica="BS>USDT>CLP",
                          capacidad_bruta=c, capacidad_neta=c, tasa_comercial=p/m, monto_cliente=p,
                          utilidad_esperada=ev["utilidad"], margen_esperado=ev["margen"],
                          estado=ev["estado"], policy_status=POLICY_PROVISIONAL,
                          alertas=ev["alertas"] + [ALERTA_POLITICA_PROVISIONAL])

    # Regla GSA: BS→CLP = 10% por encima del límite BS/CLP.
    t = _num(tasa_bs_por_clp, "tasa_bs_por_clp")
    p = m / t
    u = c - p
    r = u / p if p else 0.0
    estado = ESTADO_RENTABLE if u > 0 else ESTADO_BLOQUEADO
    alertas = [] if u > 0 else [ALERTA_OPERACION_NO_RENTABLE]
    return _resultado("BS_CLP", m, "BS", "CLP", ruta_economica="BS>USDT>CLP",
                      capacidad_bruta=c, capacidad_neta=c, tasa_comercial=t, monto_cliente=p,
                      utilidad_esperada=u, margen_esperado=r,
                      estado=estado, policy_status=POLICY_DEFINITIVA,
                      alertas=alertas, unidad_tasa="BS/CLP")


def _tasa_tramo_clp_cop(monto_clp: float) -> float:
    for limite, tasa in CLP_COP_TRAMOS:
        if monto_clp <= limite:
            return tasa
    raise AssertionError("tramo no encontrado")


# 3
def cotizar_clp_cop(monto_clp: float, capacidad_cop_por_clp: float, *,
                    permitir_captacion: bool = True, costos_pendientes: float = 0.0,
                    tasa_cliente: Optional[float] = None) -> Dict[str, Any]:
    m = _num(monto_clp, "monto_clp")
    k = _num(capacidad_cop_por_clp, "capacidad_cop_por_clp")
    c = m * k
    tasa = float(tasa_cliente) if tasa_cliente is not None else _tasa_tramo_clp_cop(m)
    p = m * tasa
    ev = evaluar_rentabilidad(c, p, costos_pendientes=costos_pendientes,
                              margen_objetivo=0.05, permitir_captacion=permitir_captacion)
    return _resultado("CLP_COP", m, "CLP", "COP", referencia_mercado=k,
                      ruta_economica="CLP>USDT>BS>COP", capacidad_bruta=c,
                      costos_totales=costos_pendientes, capacidad_neta=c,
                      tasa_comercial=tasa, monto_cliente=p,
                      utilidad_esperada=ev["utilidad"], margen_esperado=ev["margen"],
                      estado=ev["estado"], alertas=ev["alertas"])


# 4
def cotizar_cop_clp(monto_cop: float, western: float, tasa_clp_cop_reuso: float,
                    *, margen_objetivo: float = MARGEN_COP_CLP, costos_ciclo_clp: float = 0.0) -> Dict[str, Any]:
    c = _num(monto_cop, "monto_cop")
    w = _num(western, "western")
    s = _num(tasa_clp_cop_reuso, "tasa_clp_cop_reuso")
    f = _num(costos_ciclo_clp, "costos_ciclo_clp", allow_zero=True)
    denom = c / s - f
    if denom <= 0:
        return _resultado("COP_CLP", c, "COP", "CLP", estado=ESTADO_BLOQUEADO,
                          alertas=[ALERTA_OPERACION_NO_RENTABLE])
    tmin = (1 + margen_objetivo) * c / denom
    tasa = max(w, tmin)
    p = c / tasa
    alertas = [ALERTA_WESTERN_BAJO_UMBRAL] if w < tmin else []
    # margen de ciclo sobre CLP entregados
    capacidad_reuso = c / s - f
    u = capacidad_reuso - p
    r = u / p
    return _resultado("COP_CLP", c, "COP", "CLP", referencia_mercado=w,
                      ruta_economica="COP>CLP (benchmark Western / reuso CLP>COP)",
                      capacidad_bruta=capacidad_reuso, capacidad_neta=capacidad_reuso,
                      tasa_comercial=tasa, monto_cliente=p, utilidad_esperada=u,
                      margen_esperado=r, estado=ESTADO_RENTABLE if u > 0 else ESTADO_BLOQUEADO,
                      alertas=alertas, tasa_minima=tmin)


# 5
def cotizar_clp_usd(monto_clp: float, dolar_observado: float, *,
                    costo_reposicion_usd_clp: Optional[float] = None) -> Dict[str, Any]:
    m = _num(monto_clp, "monto_clp")
    obs = _num(dolar_observado, "dolar_observado")
    tasa = obs + SPREAD_USD_CLP
    alertas = []
    estado = ESTADO_RENTABLE
    if costo_reposicion_usd_clp is not None and tasa <= float(costo_reposicion_usd_clp):
        estado = ESTADO_BLOQUEADO
        alertas = [ALERTA_COSTO_REPOSICION, ALERTA_OPERACION_NO_RENTABLE]
    usd = m / tasa
    return _resultado("CLP_USD", m, "CLP", "USD", referencia_mercado=obs,
                      tasa_comercial=tasa, monto_cliente=usd, estado=estado, alertas=alertas)


# 6
def cotizar_usd_clp(monto_usd: float, dolar_observado: float) -> Dict[str, Any]:
    m = _num(monto_usd, "monto_usd")
    obs = _num(dolar_observado, "dolar_observado")
    tasa = obs - SPREAD_USD_CLP
    p = m * tasa
    return _resultado("USD_CLP", m, "USD", "CLP", referencia_mercado=obs,
                      tasa_comercial=tasa, monto_cliente=p, estado=ESTADO_CAPTACION)


# 7
def cotizar_clp_usdt(monto_clp: float, *, precio_maker_neto: Optional[float] = None,
                     precio_taker_neto: Optional[float] = None, maker_disponible: bool = False,
                     taker_disponible: bool = False, modo: str = "AUTO") -> Dict[str, Any]:
    m = _num(monto_clp, "monto_clp")
    ex = evaluar_ejecucion_p2p("COMPRA", precio_maker=precio_maker_neto, maker_disponible=maker_disponible,
                               precio_taker=precio_taker_neto, taker_disponible=taker_disponible, modo=modo)
    if not ex["ok"]:
        return _resultado("CLP_USDT", m, "CLP", "USDT", estado=ESTADO_BLOQUEADO, alertas=ex["alertas"])
    k = ex["valor_neto"]
    tasa = k + SPREAD_CLP_USDT
    usdt = m / tasa
    utilidad = usdt * SPREAD_CLP_USDT
    return _resultado("CLP_USDT", m, "CLP", "USDT", referencia_mercado=k,
                      ruta_economica="CLP>USDT P2P", modo_ejecucion=ex["modo"],
                      capacidad_neta=m/k, tasa_comercial=tasa, monto_cliente=usdt,
                      utilidad_esperada=utilidad, margen_esperado=SPREAD_CLP_USDT/k,
                      alertas=ex["alertas"], referencia_ejecucion=k)


# 8
def cotizar_usdt_clp(monto_usdt: float, *, capacidad_maker: Optional[float] = None,
                     capacidad_taker: Optional[float] = None, maker_disponible: bool = False,
                     taker_disponible: bool = False, modo: str = "AUTO") -> Dict[str, Any]:
    m = _num(monto_usdt, "monto_usdt")
    ex = evaluar_ejecucion_p2p("VENTA", precio_maker=capacidad_maker, maker_disponible=maker_disponible,
                               precio_taker=capacidad_taker, taker_disponible=taker_disponible, modo=modo)
    if not ex["ok"]:
        return _resultado("USDT_CLP", m, "USDT", "CLP", estado=ESTADO_BLOQUEADO, alertas=ex["alertas"])
    k = ex["valor_neto"]
    tasa = k - SPREAD_USDT_CLP
    c = m * k
    p = m * tasa
    u = c - p
    return _resultado("USDT_CLP", m, "USDT", "CLP", referencia_mercado=k,
                      ruta_economica="USDT>CLP P2P", modo_ejecucion=ex["modo"],
                      capacidad_bruta=c, capacidad_neta=c, tasa_comercial=tasa, monto_cliente=p,
                      utilidad_esperada=u, margen_esperado=u/p, alertas=ex["alertas"])


# 9
def cotizar_western_cop(monto_nominal_cop: float, *, costos_ejecucion: float = 0.0) -> Dict[str, Any]:
    n = _num(monto_nominal_cop, "monto_nominal_cop")
    f = _num(costos_ejecucion, "costos_ejecucion", allow_zero=True)
    com = n * COMISION_GSA_WESTERN
    p = n * (1 - COMISION_GSA_WESTERN)
    u = com - f
    estado = ESTADO_RENTABLE if u > 0 else ESTADO_BLOQUEADO
    alertas = [] if u > 0 else [ALERTA_OPERACION_NO_RENTABLE]
    return _resultado("WESTERN_COP", n, "ORIGEN", "COP", capacidad_bruta=n,
                      costos_totales=f, capacidad_neta=n-f, tasa_comercial=1-COMISION_GSA_WESTERN,
                      monto_cliente=p, utilidad_esperada=u, margen_esperado=u/n,
                      estado=estado, alertas=alertas, comision_gsa=com)


# 10
def cotizar_cop_bs(monto_cop: float, capacidad_bs: float,
                   *, margen: float = MARGEN_COP_BS_PROVISIONAL) -> Dict[str, Any]:
    m = _num(monto_cop, "monto_cop")
    c = _num(capacidad_bs, "capacidad_bs")
    p = c / (1 + margen)
    ev = evaluar_rentabilidad(c, p, margen_objetivo=margen)
    return _resultado("COP_BS", m, "COP", "BS", ruta_economica="COP>USDT>BS",
                      capacidad_bruta=c, capacidad_neta=c, tasa_comercial=p/m, monto_cliente=p,
                      utilidad_esperada=ev["utilidad"], margen_esperado=ev["margen"],
                      estado=ev["estado"], policy_status=POLICY_PROVISIONAL,
                      alertas=ev["alertas"]+[ALERTA_POLITICA_PROVISIONAL])


# 11
def cotizar_bs_cop(monto_bs: float, capacidad_binance_cop: float,
                   *, capacidad_directa_cop: Optional[float] = None,
                   directa_disponible: bool = False, margen: float = MARGEN_BS_COP_PROVISIONAL) -> Dict[str, Any]:
    m = _num(monto_bs, "monto_bs")
    cb = _num(capacidad_binance_cop, "capacidad_binance_cop")
    rutas = {"BINANCE": cb}
    if directa_disponible and capacidad_directa_cop is not None:
        rutas["DIRECTA"] = _num(capacidad_directa_cop, "capacidad_directa_cop")
    ruta = max(rutas, key=rutas.get)
    c = rutas[ruta]
    p = c / (1 + margen)
    ev = evaluar_rentabilidad(c, p, margen_objetivo=margen)
    return _resultado("BS_COP", m, "BS", "COP", ruta_economica=ruta,
                      capacidad_bruta=c, capacidad_neta=c, tasa_comercial=p/m, monto_cliente=p,
                      utilidad_esperada=ev["utilidad"], margen_esperado=ev["margen"],
                      estado=ev["estado"], policy_status=POLICY_PROVISIONAL,
                      alertas=ev["alertas"]+[ALERTA_POLITICA_PROVISIONAL])


# 12
def cotizar_usd_bs(monto_usd: float, referencia_binance_bs: float, *,
                   valor_economico_usd_bs: float, cuenta_origen: str = "",
                   mismo_banco: bool = True) -> Dict[str, Any]:
    m = _num(monto_usd, "monto_usd")
    ref = _num(referencia_binance_bs, "referencia_binance_bs")
    ve = _num(valor_economico_usd_bs, "valor_economico_usd_bs")
    tasa = ref - SPREAD_COMPRA_USD_BS
    p = m * tasa
    fee = calcular_fee_pago_bs(p, cuenta_origen, mismo_banco)
    c = m * ve
    u = c - p - fee
    estado = ESTADO_RENTABLE if u > 0 else ESTADO_BLOQUEADO
    alertas = []
    if fee:
        alertas.append(ALERTA_BANESCO_003)
    if u <= 0:
        alertas += [ALERTA_COSTO_REPOSICION, ALERTA_OPERACION_NO_RENTABLE]
    return _resultado("USD_BS", m, "USD", "BS", referencia_mercado=ref,
                      capacidad_bruta=c, costos_totales=fee, capacidad_neta=c,
                      tasa_comercial=tasa, monto_cliente=p, utilidad_esperada=u,
                      margen_esperado=u/p, estado=estado, alertas=alertas)


# 13
def cotizar_bs_usd(monto_bs: float, tasa_comercial_bs_usd: float, *,
                   costo_reposicion_bs_usd: float) -> Dict[str, Any]:
    m = _num(monto_bs, "monto_bs")
    t = _num(tasa_comercial_bs_usd, "tasa_comercial_bs_usd")
    cr = _num(costo_reposicion_bs_usd, "costo_reposicion_bs_usd")
    usd = m / t
    costo = usd * cr
    u = m - costo
    estado = ESTADO_RENTABLE if u > 0 else ESTADO_BLOQUEADO
    alertas = [] if u > 0 else [ALERTA_COSTO_REPOSICION, ALERTA_OPERACION_NO_RENTABLE]
    return _resultado("BS_USD", m, "BS", "USD", tasa_comercial=t,
                      monto_cliente=usd, utilidad_esperada=u, margen_esperado=u/costo if costo else 0,
                      estado=estado, alertas=alertas, costo_reposicion=costo)


def calcular_corredor_usd_cop(mercado_compra: float, mercado_venta: float,
                              alpha: float = ALPHA_USD_COP) -> Dict[str, Any]:
    mc = _num(mercado_compra, "mercado_compra")
    mv = _num(mercado_venta, "mercado_venta")
    a = _num(alpha, "alpha", allow_zero=True)
    if mv <= mc or a > 1:
        return {"estado": ESTADO_BLOQUEADO, "alertas": [ALERTA_MERCADO_FISICO_INVALIDO]}
    s = mv - mc
    pm = (mc + mv) / 2
    compra = pm - (s / 2 * a)
    venta = pm + (s / 2 * a)
    return {"estado": ESTADO_RENTABLE, "alertas": [], "compra": compra, "venta": venta,
            "punto_medio": pm, "spread_mercado": s}


# 14
def cotizar_usd_cop(monto_usd: float, mercado_compra: float, mercado_venta: float,
                    *, alpha: float = ALPHA_USD_COP,
                    valor_economico_min_usd_cop: Optional[float] = None) -> Dict[str, Any]:
    m = _num(monto_usd, "monto_usd")
    cor = calcular_corredor_usd_cop(mercado_compra, mercado_venta, alpha)
    if cor["estado"] == ESTADO_BLOQUEADO:
        return _resultado("USD_COP", m, "USD", "COP", estado=ESTADO_BLOQUEADO, alertas=cor["alertas"])
    tasa = cor["compra"]
    p = m * tasa
    estado = ESTADO_RENTABLE
    alertas = []
    if valor_economico_min_usd_cop is not None and tasa < float(valor_economico_min_usd_cop):
        estado = ESTADO_BLOQUEADO
        alertas = [ALERTA_COSTO_REPOSICION, ALERTA_OPERACION_NO_RENTABLE]
    return _resultado("USD_COP", m, "USD", "COP", referencia_mercado=mercado_compra,
                      tasa_comercial=tasa, monto_cliente=p, estado=estado, alertas=alertas)


# 15
def cotizar_cop_usd(monto_cop: float, mercado_compra: float, mercado_venta: float,
                    *, alpha: float = ALPHA_USD_COP, costo_reposicion_usd_cop: float) -> Dict[str, Any]:
    m = _num(monto_cop, "monto_cop")
    cr = _num(costo_reposicion_usd_cop, "costo_reposicion_usd_cop")
    cor = calcular_corredor_usd_cop(mercado_compra, mercado_venta, alpha)
    if cor["estado"] == ESTADO_BLOQUEADO:
        return _resultado("COP_USD", m, "COP", "USD", estado=ESTADO_BLOQUEADO, alertas=cor["alertas"])
    tasa = cor["venta"]
    usd = m / tasa
    costo = usd * cr
    u = m - costo
    estado = ESTADO_RENTABLE if u > 0 else ESTADO_BLOQUEADO
    alertas = [] if u > 0 else [ALERTA_COSTO_REPOSICION, ALERTA_OPERACION_NO_RENTABLE]
    return _resultado("COP_USD", m, "COP", "USD", tasa_comercial=tasa,
                      monto_cliente=usd, utilidad_esperada=u, margen_esperado=u/costo if costo else 0,
                      estado=estado, alertas=alertas, costo_reposicion=costo)


# 16
def cotizar_usdt_cop(monto_usdt: float, *, capacidad_maker: Optional[float] = None,
                     capacidad_taker: Optional[float] = None, maker_disponible: bool = False,
                     taker_disponible: bool = False, modo: str = "AUTO") -> Dict[str, Any]:
    m = _num(monto_usdt, "monto_usdt")
    ex = evaluar_ejecucion_p2p("VENTA", precio_maker=capacidad_maker, maker_disponible=maker_disponible,
                               precio_taker=capacidad_taker, taker_disponible=taker_disponible, modo=modo)
    if not ex["ok"]:
        return _resultado("USDT_COP", m, "USDT", "COP", estado=ESTADO_BLOQUEADO, alertas=ex["alertas"])
    k = ex["valor_neto"]
    tasa = k * (1 - SPREAD_USDT_COP)
    c = m * k
    p = m * tasa
    u = c - p
    return _resultado("USDT_COP", m, "USDT", "COP", referencia_mercado=k,
                      ruta_economica="USDT>COP P2P", modo_ejecucion=ex["modo"],
                      capacidad_bruta=c, capacidad_neta=c, tasa_comercial=tasa,
                      monto_cliente=p, utilidad_esperada=u, margen_esperado=u/p,
                      estado=ESTADO_RENTABLE, policy_status=POLICY_PROVISIONAL,
                      alertas=ex["alertas"]+[ALERTA_SPREAD_PROVISIONAL_1])


# 17
def cotizar_usdt_usd(monto_usd_deseado: float, *, costo_economico_usdt_por_usd: float) -> Dict[str, Any]:
    usd = _num(monto_usd_deseado, "monto_usd_deseado")
    costo_unit = _num(costo_economico_usdt_por_usd, "costo_economico_usdt_por_usd")
    usdt_cliente = usd * (1 + MARGEN_USDT_USD)
    costo = usd * costo_unit
    u = usdt_cliente - costo
    estado = ESTADO_RENTABLE if u > 0 else ESTADO_BLOQUEADO
    alertas = [] if u > 0 else [ALERTA_COSTO_REPOSICION, ALERTA_OPERACION_NO_RENTABLE]
    return _resultado("USDT_USD", usdt_cliente, "USDT", "USD",
                      tasa_comercial=1 + MARGEN_USDT_USD, monto_cliente=usd,
                      utilidad_esperada=u, margen_esperado=u/costo if costo else 0,
                      estado=estado, alertas=alertas, costo_economico=costo)


# 18
def cotizar_usd_usdt(monto_usd: float, *, necesidad_usd: str = "ALTA",
                     costo_usdt: float = 1.0) -> Dict[str, Any]:
    usd = _num(monto_usd, "monto_usd")
    c = _num(costo_usdt, "costo_usdt")
    usdt = usd
    u = usd - (usd * c)
    necesidad = str(necesidad_usd).upper()
    if necesidad == "ALTA" and abs(u) < 1e-12:
        estado = ESTADO_ESTRATEGICA
        alertas = ["MARGEN_CERO_INTENCIONAL"]
    elif u < 0 or necesidad in {"EXCESIVA", "BAJA"}:
        estado = ESTADO_NO_RECOMENDADO
        alertas = [ALERTA_INVENTARIO] + ([ALERTA_OPERACION_NO_RENTABLE] if u < 0 else [])
    else:
        estado = ESTADO_RENTABLE
        alertas = []
    return _resultado("USD_USDT", usd, "USD", "USDT", tasa_comercial=1.0,
                      monto_cliente=usdt, utilidad_esperada=u, margen_esperado=u/usdt,
                      estado=estado, alertas=alertas)
