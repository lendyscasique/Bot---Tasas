"""Motor referencial de pricing CLP→COP / BS→COP para GSA Cambios.

V1.0: sin inventario, CPP, ERP ni dependencia de Western para formar precio.
Western se usa exclusivamente como benchmark comercial.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

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
