# ══════════════════════════════════════════════════════════════════════
# FASE 1B.0 — REPOSITORIOS BLINDADOS DEL MOTOR DE INVENTARIO
# GSA Cambios — capa adicional, resuelve Riesgos R1, R2 y R6 de la
# auditoría de Fase 1A. Reemplaza a repositorios_inventario.py de 1A.
# ══════════════════════════════════════════════════════════════════════
"""
Esta fase es EXCLUSIVAMENTE blindaje estructural. NO se agrega ninguna
lógica de negocio nueva respecto a Fase 1A:
- NO se calcula costo promedio ponderado.
- NO se implementan entradas ni salidas con efecto en stock real.
- NO se calculan utilidades.
- NO se valida stock negativo (sigue sin CHECK constraint, según diseño
  documentado: la decisión de cuándo y cómo validar stock negativo
  pertenece a una fase posterior).
- NO se hace reconstrucción histórica.

Lo que SÍ cambia respecto al repositorio de Fase 1A:

R1 resuelto — InventarioActualRepo separado en 3 métodos explícitos:
    crear()             -> solo para la primera vez que una moneda
                           obtiene una fila. Genera id nuevo.
    actualizar()         -> identifica la fila por moneda, nunca por id.
                           NUNCA envía el campo 'id' en el payload,
                           por lo que Postgres no lo puede modificar.
    upsert_por_moneda()  -> conveniencia que decide internamente si
                           crear() o actualizar(), pero igualmente
                           nunca permite que un update cambie el id.
    El método guardar() de Fase 1A queda DEPRECADO (se mantiene por
    compatibilidad pero internamente delega a upsert_por_moneda()
    con una advertencia), para no romper si algo ya lo invocó.

R2 resuelto — Los 3 métodos de escritura de InventarioActualRepo
    (crear, actualizar, upsert_por_moneda) usan el lock de
    locks_inventario.py y son seguros para llamarse desde múltiples
    hilos sin perder actualizaciones. La sección crítica (leer
    estado actual + decidir + escribir) ocurre dentro del lock de
    la moneda correspondiente.

R6 resuelto — Toda la serialización hacia Supabase usa un encoder
    JSON personalizado (_DecimalAsStringEncoder) que convierte
    Decimal a string en lugar de float, preservando la precisión
    exacta hasta el límite de NUMERIC(18,8) de Postgres. PostgREST
    acepta valores numéricos enviados como string sin pérdida.

Repositorios mantenidos INDEPENDIENTES de bot.py por requisito
explícito de esta fase: no se reutiliza supa_select/supa_insert.
"""

import os
import json
import requests
from typing import Optional, List, Union
from datetime import date
from decimal import Decimal

from modelos_inventario import (
    InventarioActual,
    InventarioMovimiento,
    LoteInventario,
    UtilidadOperacion,
    OperacionComponente,
    MonedaInventario,
)
from locks_inventario import lock_moneda

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


# ════════════════════════════════════════════════════════════════════
# R6 -- Serialización sin pérdida de precisión
# ════════════════════════════════════════════════════════════════════
class _DecimalAsStringEncoder(json.JSONEncoder):
    """
    Encoder JSON que convierte Decimal a string en lugar de float.

    Por qué string y no float: float es IEEE-754 binario y no puede
    representar exactamente la mayoría de los decimales (ej. 101.67
    en binario es una aproximación). PostgREST/Postgres, al recibir
    un campo NUMERIC como string en el JSON, lo parsea directamente
    sin pasar por una conversión binaria intermedia, preservando los
    hasta 8 decimales que NUMERIC(18,8) permite.
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            # IMPORTANTE: str(Decimal) usa notación científica para
            # valores muy pequeños (ej. Decimal("0.00000001") -> "1E-8"),
            # y PostgREST no acepta notación científica como literal
            # NUMERIC válido. format(obj, 'f') fuerza notación decimal
            # fija ("0.00000001"), que es lo que Postgres espera.
            return format(obj, "f")
        return super().default(obj)


def _to_json_payload(data: Union[dict, list]) -> str:
    """Serializa un dict o lista de dicts a JSON usando el encoder
    que preserva precisión de Decimal. Punto único de serialización
    para todo este módulo."""
    return json.dumps(data, cls=_DecimalAsStringEncoder)


# ════════════════════════════════════════════════════════════════════
# Funciones HTTP internas — mismo comportamiento que Fase 1A, pero
# ahora serializan con _DecimalAsStringEncoder en vez de requests json=
# ════════════════════════════════════════════════════════════════════

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
        print(f"[WARN] [{tabla}] GET status={r.status_code}: {r.text[:200]}")
        return []
    except Exception as e:
        print(f"[ERROR] [{tabla}] GET error: {e}")
        return []


def _post(tabla: str, payload: Union[dict, list], on_conflict: str = "", prefer: str = "return=representation") -> Optional[List[dict]]:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    try:
        url = f"{SUPABASE_URL}/rest/v1/{tabla}"
        if on_conflict:
            url += f"?on_conflict={on_conflict}"
            prefer = f"resolution=merge-duplicates,{prefer}"
        r = requests.post(
            url,
            headers=_headers(prefer),
            data=_to_json_payload(payload),
            timeout=15,
        )
        if r.status_code in (200, 201):
            return r.json() if r.text else []
        print(f"[WARN] [{tabla}] POST status={r.status_code}: {r.text[:300]}")
        return None
    except Exception as e:
        print(f"[ERROR] [{tabla}] POST error: {e}")
        return None


def _patch(tabla: str, query: str, payload: dict) -> bool:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return False
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{tabla}?{query}",
            headers=_headers("return=minimal"),
            data=_to_json_payload(payload),
            timeout=15,
        )
        if r.status_code in (200, 204):
            return True
        print(f"[WARN] [{tabla}] PATCH status={r.status_code}: {r.text[:300]}")
        return False
    except Exception as e:
        print(f"[ERROR] [{tabla}] PATCH error: {e}")
        return False


# ════════════════════════════════════════════════════════════════════
# REPOSITORIO: InventarioActualRepo
# Reescrito para resolver R1 (id inmutable) y R2 (atomicidad por moneda)
# ════════════════════════════════════════════════════════════════════
class InventarioActualRepo:
    """
    Acceso de lectura/escritura a la tabla inventario_actual.
    Una fila por moneda. Esta fase NO calcula los valores que se
    guardan -- solo garantiza CÓMO se guardan de forma segura.
    """

    TABLA = "inventario_actual"

    @staticmethod
    def obtener(moneda: MonedaInventario) -> Optional[InventarioActual]:
        """Lectura simple, sin lock -- leer no compite por escritura.
        El lock se aplica en los métodos que escriben, donde existe
        el riesgo real de condición de carrera."""
        rows = _get(InventarioActualRepo.TABLA, f"moneda=eq.{moneda}&limit=1")
        if rows:
            return InventarioActual.from_dict(rows[0])
        return None

    @staticmethod
    def listar_todas() -> List[InventarioActual]:
        rows = _get(InventarioActualRepo.TABLA, "order=moneda.asc")
        return [InventarioActual.from_dict(r) for r in rows]

    @staticmethod
    def crear(inv: InventarioActual) -> bool:
        """
        Inserta una fila NUEVA para una moneda que todavía no tiene
        registro en inventario_actual. El id viaja en el payload
        porque es la primera (y única) vez que esa fila adquiere
        identidad -- coherente con "el id se genera únicamente en
        el primer insert".

        Bajo lock de la moneda: si dos hilos intentan crear() la
        misma moneda simultáneamente, el lock serializa el intento;
        si la fila ya existe, además la UNIQUE constraint de
        Fase 1A sobre 'moneda' rechazaría el segundo insert.
        """
        with lock_moneda(inv.moneda):
            existente = InventarioActualRepo.obtener(inv.moneda)
            if existente is not None:
                print(
                    f"[WARN] InventarioActualRepo.crear(): la moneda '{inv.moneda}' "
                    f"ya tiene una fila (id={existente.id}). Use actualizar() "
                    f"en su lugar. No se modificó nada."
                )
                return False

            resultado = _post(InventarioActualRepo.TABLA, inv.to_dict())
            return resultado is not None

    @staticmethod
    def actualizar(moneda: MonedaInventario, stock_actual=None, costo_promedio=None,
                   valor_inventario=None, ultima_actualizacion=None) -> bool:
        """
        Actualiza la fila existente de una moneda IDENTIFICÁNDOLA POR
        MONEDA, nunca por id. El campo 'id' JAMÁS se incluye en este
        payload -- por construcción esta función no tiene forma de
        enviarlo, ni siquiera por error, porque no es uno de sus
        parámetros. Esto es lo que garantiza que un update nunca
        pueda regenerar ni alterar el UUID original de la fila.

        Solo los campos efectivamente pasados (distintos de None) se
        incluyen en el PATCH -- permite actualizaciones parciales.

        Bajo lock de la moneda: esta es la operación central que
        resuelve R2. Cualquier código futuro que necesite hacer
        "leer -> calcular nuevo CPP -> escribir" debe envolver TODO
        ese ciclo dentro de `with lock_moneda(moneda):` y llamar a
        este método para la escritura final.
        """
        from modelos_inventario import MONEDAS_SOPORTADAS
        if moneda not in MONEDAS_SOPORTADAS:
            print(f"[WARN] InventarioActualRepo.actualizar(): moneda '{moneda}' no reconocida.")
            return False

        payload = {}
        if stock_actual is not None:
            payload["stock_actual"] = stock_actual
        if costo_promedio is not None:
            payload["costo_promedio"] = costo_promedio
        if valor_inventario is not None:
            payload["valor_inventario"] = valor_inventario
        if ultima_actualizacion is not None:
            payload["ultima_actualizacion"] = (
                ultima_actualizacion.isoformat()
                if hasattr(ultima_actualizacion, "isoformat")
                else ultima_actualizacion
            )

        if not payload:
            print("[WARN] InventarioActualRepo.actualizar(): nada que actualizar.")
            return False

        assert "id" not in payload, "Invariante violado: 'id' nunca debe viajar en un update."

        with lock_moneda(moneda):
            return _patch(
                InventarioActualRepo.TABLA,
                f"moneda=eq.{moneda}",
                payload,
            )

    @staticmethod
    def upsert_por_moneda(moneda: MonedaInventario, stock_actual=None, costo_promedio=None,
                           valor_inventario=None) -> bool:
        """
        Conveniencia: decide automáticamente si la moneda necesita
        crear() (no existe fila aún) o actualizar() (ya existe).

        Todo el ciclo decisión+escritura ocurre bajo el lock de la
        moneda, para que dos hilos no decidan "no existe, voy a
        crear" al mismo tiempo.
        """
        with lock_moneda(moneda):
            existente = InventarioActualRepo.obtener(moneda)

            if existente is None:
                nuevo = InventarioActual(
                    moneda=moneda,
                    stock_actual=stock_actual if stock_actual is not None else Decimal("0"),
                    costo_promedio=costo_promedio if costo_promedio is not None else Decimal("0"),
                    valor_inventario=valor_inventario if valor_inventario is not None else Decimal("0"),
                )
                resultado = _post(InventarioActualRepo.TABLA, nuevo.to_dict())
                return resultado is not None

            payload = {}
            if stock_actual is not None:
                payload["stock_actual"] = stock_actual
            if costo_promedio is not None:
                payload["costo_promedio"] = costo_promedio
            if valor_inventario is not None:
                payload["valor_inventario"] = valor_inventario

            if not payload:
                return True

            assert "id" not in payload, "Invariante violado: 'id' nunca debe viajar en un update."

            return _patch(
                InventarioActualRepo.TABLA,
                f"moneda=eq.{moneda}",
                payload,
            )

    @staticmethod
    def guardar(inv: InventarioActual) -> bool:
        """
        DEPRECADO desde Fase 1B.0 -- mantenido únicamente por
        compatibilidad retroactiva. Internamente delega a
        upsert_por_moneda() sin enviar el campo 'id' del modelo
        recibido, eliminando el riesgo original (R1).

        Código nuevo debe usar crear() / actualizar() /
        upsert_por_moneda() directamente, no este método.
        """
        print(
            "[WARN] InventarioActualRepo.guardar() está deprecado desde Fase 1B.0. "
            "Use crear(), actualizar() o upsert_por_moneda() en su lugar."
        )
        return InventarioActualRepo.upsert_por_moneda(
            moneda=inv.moneda,
            stock_actual=inv.stock_actual,
            costo_promedio=inv.costo_promedio,
            valor_inventario=inv.valor_inventario,
        )


# ════════════════════════════════════════════════════════════════════
# REPOSITORIO: InventarioMovimientosRepo
# Sin cambios funcionales respecto a Fase 1A -- la tabla ahora tiene
# UNIQUE constraint (migración 002): un duplicado exacto será
# rechazado por Postgres en vez de aceptado silenciosamente.
# ════════════════════════════════════════════════════════════════════
class InventarioMovimientosRepo:
    """Acceso a la tabla inventario_movimientos. Append-only:
    no se expone ningún método de actualización ni borrado."""

    TABLA = "inventario_movimientos"

    @staticmethod
    def insertar(mov: InventarioMovimiento) -> bool:
        resultado = _post(InventarioMovimientosRepo.TABLA, mov.to_dict())
        return resultado is not None

    @staticmethod
    def insertar_lote(movimientos: List[InventarioMovimiento]) -> bool:
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
# REPOSITORIO: LotesInventarioRepo -- sin cambios respecto a Fase 1A
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
        rows = _get(
            LotesInventarioRepo.TABLA,
            f"moneda=eq.{moneda}&estado=in.(ABIERTO,PARCIAL)&order=fecha.asc",
        )
        return [LoteInventario.from_dict(r) for r in rows]

    @staticmethod
    def actualizar_consumo(lote_id: str, cantidad_consumida, cantidad_disponible, estado: str) -> bool:
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
# REPOSITORIO: UtilidadesOperacionesRepo -- sin cambios funcionales.
# UNIQUE(referencia_operacion, moneda) ya activo (migración 002).
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
# REPOSITORIO: OperacionComponentesRepo -- sin cambios funcionales.
# UNIQUE(operacion_id, secuencia) ya activo (migración 002).
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
