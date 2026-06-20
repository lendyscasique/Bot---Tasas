# ══════════════════════════════════════════════════════════════════════
# FASE 1B.0 — LOCKS DE INVENTARIO POR MONEDA
# GSA Cambios — capa adicional, resuelve Riesgo R2 de la auditoría
# de Fase 1A (lectura-cálculo-escritura no atómica / condición de carrera)
# ══════════════════════════════════════════════════════════════════════
"""
Este módulo SOLO provee infraestructura de exclusión mutua por moneda.

NO implementa:
- cálculo de costo promedio ponderado
- entradas ni salidas de inventario
- utilidades
- validación de stock negativo
- reconstrucción histórica

Su única responsabilidad es garantizar que, cuando en fases futuras se
implemente el patrón "leer estado actual → calcular nuevo estado →
escribir", ese ciclo completo se ejecute bajo exclusión mutua para una
moneda dada — de forma que dos hilos no puedan operar sobre el mismo
saldo de inventario simultáneamente y perder una actualización.

Se usa threading.Lock() (no PL/pgSQL ni locks a nivel de base de datos)
porque así lo especifica el alcance de esta fase: la atomicidad se
resuelve en la capa de aplicación del bot, que ya corre en un único
proceso Python con múltiples hilos (confirmado en bot.py: loops de
mercado, tasas, reportes, y cada mensaje de Telegram se procesa en
threads independientes).

USO PREVISTO (en fases futuras, NO en esta):

    from locks_inventario import obtener_lock

    with obtener_lock("USDT"):
        # leer inventario_actual de USDT
        # calcular nuevo CPP
        # escribir inventario_actual de USDT
        # (todo esto bajo el mismo lock, ningún otro hilo puede
        #  entrar a esta sección para la moneda USDT mientras tanto)

Cada moneda tiene su PROPIO lock independiente — una operación sobre
COP nunca espera a que termine una operación sobre USDT. Esto evita
que el sistema completo se vuelva secuencial por una sola moneda
ocupada.
"""

import threading
from typing import Dict
from contextlib import contextmanager

# Mismo conjunto de monedas que en modelos_inventario.py — duplicado
# intencionalmente aquí para mantener este módulo sin dependencias
# externas (ni del bot, ni de modelos_inventario), tal como exige el
# requisito de repositorios independientes de esta fase.
MONEDAS_SOPORTADAS = ("USDT", "COP", "CLP", "USD", "VES")

# ──────────────────────────────────────────────────────────────────
# Registro de locks — un Lock() por moneda, creado una sola vez al
# importar el módulo. No se crean locks dinámicamente por petición,
# para evitar el problema clásico de "cada hilo crea su propio lock
# y la exclusión mutua nunca ocurre realmente".
# ──────────────────────────────────────────────────────────────────
_locks_por_moneda: Dict[str, threading.Lock] = {
    moneda: threading.Lock() for moneda in MONEDAS_SOPORTADAS
}

# Lock adicional que protege la creación de nuevas entradas en el
# diccionario de locks, por si en el futuro se soporta una moneda
# que no estaba en MONEDAS_SOPORTADAS al arrancar el proceso.
_lock_registro = threading.Lock()


def obtener_lock(moneda: str) -> threading.Lock:
    """
    Retorna el Lock() correspondiente a una moneda específica.

    Si la moneda ya está en MONEDAS_SOPORTADAS, retorna el lock
    pre-creado (caso esperado y normal).

    Si la moneda no estaba pre-registrada, la crea de forma segura
    bajo _lock_registro para evitar que dos hilos creen dos locks
    distintos para la misma moneda nueva en una condición de carrera
    de inicialización (race condition al crear el propio lock).

    Esta función NO valida si la moneda es "válida" en términos de
    negocio (eso es responsabilidad de modelos_inventario.py). Aquí
    solo se garantiza que, sea cual sea el string recibido, siempre
    se devuelve el MISMO objeto Lock para ese string en todo el
    ciclo de vida del proceso.
    """
    if moneda in _locks_por_moneda:
        return _locks_por_moneda[moneda]

    with _lock_registro:
        # Volver a verificar dentro del lock: otro hilo pudo haberlo
        # creado mientras este esperaba a entrar aquí.
        if moneda not in _locks_por_moneda:
            _locks_por_moneda[moneda] = threading.Lock()
        return _locks_por_moneda[moneda]


@contextmanager
def lock_moneda(moneda: str, timeout: float = 10.0):
    """
    Context manager de conveniencia equivalente a usar
    `with obtener_lock(moneda):` directamente, pero con soporte
    de timeout explícito para evitar que un bloqueo nunca liberado
    cuelgue el proceso indefinidamente.

    Lanza TimeoutError si no se pudo adquirir el lock dentro del
    tiempo especificado — esto es preferible a un bloqueo infinito
    silencioso en un bot que debe seguir respondiendo a Telegram.

    Uso futuro previsto:

        with lock_moneda("USDT"):
            ... operación crítica sobre el inventario de USDT ...
    """
    lock = obtener_lock(moneda)
    adquirido = lock.acquire(timeout=timeout)
    if not adquirido:
        raise TimeoutError(
            f"No se pudo adquirir el lock de inventario para '{moneda}' "
            f"dentro de {timeout}s. Posible bloqueo prolongado por otra "
            f"operación concurrente sobre la misma moneda."
        )
    try:
        yield lock
    finally:
        lock.release()


def locks_activos() -> Dict[str, bool]:
    """
    Utilidad de diagnóstico: retorna qué monedas tienen su lock
    actualmente adquirido (True) o libre (False).

    locked() es no-bloqueante — no intenta adquirir el lock, solo
    consulta su estado actual. Útil para un futuro comando de
    diagnóstico tipo /inventario_status sin afectar la concurrencia.
    """
    return {moneda: lock.locked() for moneda, lock in _locks_por_moneda.items()}
