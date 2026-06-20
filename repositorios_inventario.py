# ══════════════════════════════════════════════════════════════════════
# FASE 1A — REPOSITORIOS SUPABASE DEL MOTOR DE INVENTARIO
# GSA Cambios — capa adicional, no modifica funciones existentes del bot
# ══════════════════════════════════════════════════════════════════════
"""
Repositorios de acceso a datos para las 5 tablas nuevas de inventario.

IMPORTANTE — Esta fase es solo infraestructura:
- NO calcula costo promedio ponderado.
- NO calcula utilidades.
- NO valida stock negativo.
- NO hace reconstrucción histórica.
Esas responsabilidades llegan en fases posteriores (1B, 1C, etc.)
y se construirán SOBRE estos repositorios, no dentro de ellos.

Estos repositorios reutilizan las mismas variables de entorno y el mismo
patrón de requests que ya usa el bot (SUPABASE_URL, SUPABASE_KEY), para
no introducir una segunda forma de conectarse a Supabase. Si se integra
este módulo dentro de bot.py, las funciones supa_* ya existentes pueden
sustituir a las funciones HTTP internas de este archivo sin cambiar las
firmas públicas de los repositorios.
"""

import os
import requests
from typing import Optional, List
from datetime import date

from modelos_inventario import (
    InventarioActual,
    InventarioMovimiento,
    LoteInventario,
    UtilidadOperacion,
    OperacionComponente,
    MonedaInventario,
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def _headers(prefer: str = "") -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _get(tabla: str, query: str = "") -> List[dict]:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{tabla}?{query}",
            headers=_headers(),
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
        print(f"⚠️ [{tabla}] GET status={r.status_code}: {r.text[:200]}")
        return []
    except Exception as e:
        print(f"❌ [{tabla}] GET error: {e}")
        return []


def _post(tabla: str, payload: dict | list, on_conflict: str = "", prefer: str = "return=representation") -> Optional[List[dict]]:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    try:
        url = f"{SUPABASE_URL}/rest/v1/{tabla}"
        if on_conflict:
            url += f"?on_conflict={on_conflict}"
            prefer = f"resolution=merge-duplicates,{prefer}"
        r = requests.post(url, headers=_headers(prefer), json=payload, timeout=15)
        if r.status_code in (200, 201):
            return r.json() if r.text else []
        print(f"⚠️ [{tabla}] POST status={r.status_code}: {r.text[:300]}")
        return None
    except Exception as e:
        print(f"❌ [{tabla}] POST error: {e}")
        return None


def _patch(tabla: str, query: str, payload: dict) -> bool:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return False
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{tabla}?{query}",
            headers=_headers("return=minimal"),
            json=payload,
            timeout=15,
        )
        if r.status_code in (200, 204):
            return True
        print(f"⚠️ [{tabla}] PATCH status={r.status_code}: {r.text[:300]}")
        return False
    except Exception as e:
        print(f"❌ [{tabla}] PATCH error: {e}")
        return False


# ════════════════════════════════════════════════════════════════════
# REPOSITORIO: InventarioActualRepo
# ════════════════════════════════════════════════════════════════════
class InventarioActualRepo:
    """Acceso de lectura/escritura a la tabla inventario_actual.
    Una fila por moneda. Esta fase NO calcula los valores — solo
    permite leer y escribir el estado tal como se le indique."""

    TABLA = "inventario_actual"

    @staticmethod
    def obtener(moneda: MonedaInventario) -> Optional[InventarioActual]:
        rows = _get(InventarioActualRepo.TABLA, f"moneda=eq.{moneda}&limit=1")
        if rows:
            return InventarioActual.from_dict(rows[0])
        return None

    @staticmethod
    def listar_todas() -> List[InventarioActual]:
        rows = _get(InventarioActualRepo.TABLA, "order=moneda.asc")
        return [InventarioActual.from_dict(r) for r in rows]

    @staticmethod
    def guardar(inv: InventarioActual) -> bool:
        """Upsert por moneda (la columna moneda es UNIQUE)."""
        resultado = _post(
            InventarioActualRepo.TABLA,
            inv.to_dict(),
            on_conflict="moneda",
        )
        return resultado is not None


# ════════════════════════════════════════════════════════════════════
# REPOSITORIO: InventarioMovimientosRepo
# ════════════════════════════════════════════════════════════════════
class InventarioMovimientosRepo:
    """Acceso a la tabla inventario_movimientos. Append-only:
    no se expone ningún método de actualización ni borrado,
    en línea con el principio de historial inmutable."""

    TABLA = "inventario_movimientos"

    @staticmethod
    def insertar(mov: InventarioMovimiento) -> bool:
        resultado = _post(InventarioMovimientosRepo.TABLA, mov.to_dict())
        return resultado is not None

    @staticmethod
    def insertar_lote(movimientos: List[InventarioMovimiento]) -> bool:
        """Inserta varios movimientos en una sola llamada HTTP."""
        if not movimientos:
            return True
        payload = [m.to_dict() for m in movimientos]
        resultado = _post(InventarioMovimientosRepo.TABLA, payload)
        return resultado is not None

    @staticmethod
    def listar_por_moneda(moneda: MonedaInventario, limite: int = 100) -> List[InventarioMovimiento]:
        rows = _get(
            InventarioMovimientosRepo.TABLA,
            f"moneda=eq.{moneda}&order=fecha.desc,created_at.desc&limit={limite}",
        )
        return [InventarioMovimiento.from_dict(r) for r in rows]

    @staticmethod
    def listar_por_fecha(fecha_inicio: date, fecha_fin: date) -> List[InventarioMovimiento]:
        rows = _get(
            InventarioMovimientosRepo.TABLA,
            f"fecha=gte.{fecha_inicio.isoformat()}&fecha=lte.{fecha_fin.isoformat()}"
            f"&order=fecha.asc,created_at.asc",
        )
        return [InventarioMovimiento.from_dict(r) for r in rows]

    @staticmethod
    def listar_por_referencia(referencia_operacion: str) -> List[InventarioMovimiento]:
        rows = _get(
            InventarioMovimientosRepo.TABLA,
            f"referencia_operacion=eq.{referencia_operacion}",
        )
        return [InventarioMovimiento.from_dict(r) for r in rows]


# ════════════════════════════════════════════════════════════════════
# REPOSITORIO: LotesInventarioRepo
# ════════════════════════════════════════════════════════════════════
class LotesInventarioRepo:
    """Acceso a la tabla lotes_inventario."""

    TABLA = "lotes_inventario"

    @staticmethod
    def insertar(lote: LoteInventario) -> bool:
        resultado = _post(LotesInventarioRepo.TABLA, lote.to_dict())
        return resultado is not None

    @staticmethod
    def listar_abiertos(moneda: MonedaInventario) -> List[LoteInventario]:
        """Lotes con saldo disponible, ordenados del más antiguo al más
        nuevo (orden natural para consumo FIFO si se llegara a usar)."""
        rows = _get(
            LotesInventarioRepo.TABLA,
            f"moneda=eq.{moneda}&estado=in.(ABIERTO,PARCIAL)&order=fecha.asc",
        )
        return [LoteInventario.from_dict(r) for r in rows]

    @staticmethod
    def actualizar_consumo(lote_id: str, cantidad_consumida: float, cantidad_disponible: float, estado: str) -> bool:
        return _patch(
            LotesInventarioRepo.TABLA,
            f"id=eq.{lote_id}",
            {
                "cantidad_consumida": cantidad_consumida,
                "cantidad_disponible": cantidad_disponible,
                "estado": estado,
            },
        )


# ════════════════════════════════════════════════════════════════════
# REPOSITORIO: UtilidadesOperacionesRepo
# ════════════════════════════════════════════════════════════════════
class UtilidadesOperacionesRepo:
    """Acceso a la tabla utilidades_operaciones."""

    TABLA = "utilidades_operaciones"

    @staticmethod
    def insertar(utilidad: UtilidadOperacion) -> bool:
        resultado = _post(UtilidadesOperacionesRepo.TABLA, utilidad.to_dict())
        return resultado is not None

    @staticmethod
    def listar_por_referencia(referencia_operacion: str) -> List[UtilidadOperacion]:
        rows = _get(
            UtilidadesOperacionesRepo.TABLA,
            f"referencia_operacion=eq.{referencia_operacion}",
        )
        return [UtilidadOperacion.from_dict(r) for r in rows]

    @staticmethod
    def listar_por_fecha(fecha_inicio: date, fecha_fin: date) -> List[UtilidadOperacion]:
        rows = _get(
            UtilidadesOperacionesRepo.TABLA,
            f"fecha=gte.{fecha_inicio.isoformat()}&fecha=lte.{fecha_fin.isoformat()}"
            f"&order=fecha.asc",
        )
        return [UtilidadOperacion.from_dict(r) for r in rows]

    @staticmethod
    def listar_por_estado(estado: str) -> List[UtilidadOperacion]:
        rows = _get(UtilidadesOperacionesRepo.TABLA, f"estado=eq.{estado}")
        return [UtilidadOperacion.from_dict(r) for r in rows]

    @staticmethod
    def actualizar_estado(utilidad_id: str, nuevo_estado: str) -> bool:
        return _patch(
            UtilidadesOperacionesRepo.TABLA,
            f"id=eq.{utilidad_id}",
            {"estado": nuevo_estado},
        )


# ════════════════════════════════════════════════════════════════════
# REPOSITORIO: OperacionComponentesRepo
# ════════════════════════════════════════════════════════════════════
class OperacionComponentesRepo:
    """Acceso a la tabla operacion_componentes."""

    TABLA = "operacion_componentes"

    @staticmethod
    def insertar(componente: OperacionComponente) -> bool:
        resultado = _post(OperacionComponentesRepo.TABLA, componente.to_dict())
        return resultado is not None

    @staticmethod
    def insertar_lote(componentes: List[OperacionComponente]) -> bool:
        if not componentes:
            return True
        payload = [c.to_dict() for c in componentes]
        resultado = _post(OperacionComponentesRepo.TABLA, payload)
        return resultado is not None

    @staticmethod
    def listar_por_operacion(operacion_id: str) -> List[OperacionComponente]:
        rows = _get(
            OperacionComponentesRepo.TABLA,
            f"operacion_id=eq.{operacion_id}&order=secuencia.asc",
        )
        return [OperacionComponente.from_dict(r) for r in rows]
