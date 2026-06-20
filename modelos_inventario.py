# ══════════════════════════════════════════════════════════════════════
# FASE 1A — MODELOS PYTHON DEL MOTOR DE INVENTARIO
# GSA Cambios — capa adicional, no modifica modelos existentes del bot
# ══════════════════════════════════════════════════════════════════════
"""
Estos modelos son representaciones tipadas (dataclasses) de las 5 tablas
nuevas creadas en 001_fase1a_infraestructura_inventario.sql

Esta fase NO implementa lógica de negocio (cálculo de CPP, utilidades,
reconstrucción histórica). Solo define la forma de los datos y provee
conversión hacia/desde dict para uso directo con los repositorios
Supabase (Fase 1B).

Monedas soportadas: USDT, COP, CLP, USD, VES
"""

from dataclasses import dataclass, field, asdict
from datetime import date, time, datetime
from typing import Optional, Literal
from decimal import Decimal
import uuid


# ──────────────────────────────────────────────────────────────────
# Tipos literales (espejo de los ENUMs de Postgres)
# ──────────────────────────────────────────────────────────────────

MonedaInventario = Literal["USDT", "COP", "CLP", "USD", "VES"]
MONEDAS_SOPORTADAS = ("USDT", "COP", "CLP", "USD", "VES")

EstadoUtilidad = Literal["PENDIENTE", "PROVISIONAL", "CERRADA", "AJUSTADA"]
EstadoComponente = Literal["PENDIENTE", "PROVISIONAL", "CERRADA", "AJUSTADA"]
EstadoLote = Literal["ABIERTO", "PARCIAL", "CONSUMIDO"]


def _nuevo_uuid() -> str:
    return str(uuid.uuid4())


def _validar_moneda(moneda: str) -> str:
    """Valida que la moneda esté en el conjunto soportado. No lanza
    excepción silenciosa: si la moneda no es válida, falla explícitamente
    para que el error se detecte en desarrollo, no en producción."""
    if moneda not in MONEDAS_SOPORTADAS:
        raise ValueError(
            f"Moneda '{moneda}' no soportada. "
            f"Debe ser una de: {MONEDAS_SOPORTADAS}"
        )
    return moneda


# ════════════════════════════════════════════════════════════════════
# MODELO 1: InventarioActual
# Fotografía actual del inventario por moneda
# ════════════════════════════════════════════════════════════════════
@dataclass
class InventarioActual:
    moneda: MonedaInventario
    stock_actual: Decimal = Decimal("0")
    costo_promedio: Decimal = Decimal("0")
    valor_inventario: Decimal = Decimal("0")
    id: str = field(default_factory=_nuevo_uuid)
    ultima_actualizacion: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        self.moneda = _validar_moneda(self.moneda)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stock_actual"] = float(self.stock_actual)
        d["costo_promedio"] = float(self.costo_promedio)
        d["valor_inventario"] = float(self.valor_inventario)
        if self.ultima_actualizacion:
            d["ultima_actualizacion"] = self.ultima_actualizacion.isoformat()
        if self.created_at:
            d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "InventarioActual":
        return cls(
            id=data.get("id", _nuevo_uuid()),
            moneda=data["moneda"],
            stock_actual=Decimal(str(data.get("stock_actual", 0) or 0)),
            costo_promedio=Decimal(str(data.get("costo_promedio", 0) or 0)),
            valor_inventario=Decimal(str(data.get("valor_inventario", 0) or 0)),
            ultima_actualizacion=data.get("ultima_actualizacion"),
            created_at=data.get("created_at"),
        )


# ════════════════════════════════════════════════════════════════════
# MODELO 2: InventarioMovimiento
# Historial inmutable de movimientos (append-only)
# ════════════════════════════════════════════════════════════════════
@dataclass
class InventarioMovimiento:
    fecha: date
    moneda: MonedaInventario
    tipo_movimiento: str
    id: str = field(default_factory=_nuevo_uuid)
    hora: Optional[time] = None
    entrada: Decimal = Decimal("0")
    salida: Decimal = Decimal("0")
    stock_anterior: Optional[Decimal] = None
    stock_final: Optional[Decimal] = None
    costo_unitario: Optional[Decimal] = None
    costo_promedio_anterior: Optional[Decimal] = None
    costo_promedio_nuevo: Optional[Decimal] = None
    valor_movimiento: Optional[Decimal] = None
    referencia_operacion: Optional[str] = None
    observaciones: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        self.moneda = _validar_moneda(self.moneda)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "fecha": self.fecha.isoformat() if isinstance(self.fecha, date) else self.fecha,
            "hora": self.hora.isoformat() if isinstance(self.hora, time) else self.hora,
            "moneda": self.moneda,
            "tipo_movimiento": self.tipo_movimiento,
            "entrada": float(self.entrada) if self.entrada is not None else 0.0,
            "salida": float(self.salida) if self.salida is not None else 0.0,
            "stock_anterior": float(self.stock_anterior) if self.stock_anterior is not None else None,
            "stock_final": float(self.stock_final) if self.stock_final is not None else None,
            "costo_unitario": float(self.costo_unitario) if self.costo_unitario is not None else None,
            "costo_promedio_anterior": float(self.costo_promedio_anterior) if self.costo_promedio_anterior is not None else None,
            "costo_promedio_nuevo": float(self.costo_promedio_nuevo) if self.costo_promedio_nuevo is not None else None,
            "valor_movimiento": float(self.valor_movimiento) if self.valor_movimiento is not None else None,
            "referencia_operacion": self.referencia_operacion,
            "observaciones": self.observaciones,
        }
        if self.created_at:
            d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "InventarioMovimiento":
        def _dec(v):
            return Decimal(str(v)) if v is not None else None

        return cls(
            id=data.get("id", _nuevo_uuid()),
            fecha=data["fecha"],
            hora=data.get("hora"),
            moneda=data["moneda"],
            tipo_movimiento=data["tipo_movimiento"],
            entrada=_dec(data.get("entrada", 0)) or Decimal("0"),
            salida=_dec(data.get("salida", 0)) or Decimal("0"),
            stock_anterior=_dec(data.get("stock_anterior")),
            stock_final=_dec(data.get("stock_final")),
            costo_unitario=_dec(data.get("costo_unitario")),
            costo_promedio_anterior=_dec(data.get("costo_promedio_anterior")),
            costo_promedio_nuevo=_dec(data.get("costo_promedio_nuevo")),
            valor_movimiento=_dec(data.get("valor_movimiento")),
            referencia_operacion=data.get("referencia_operacion"),
            observaciones=data.get("observaciones"),
            created_at=data.get("created_at"),
        )


# ════════════════════════════════════════════════════════════════════
# MODELO 3: LoteInventario
# Lote individual de entrada, para trazabilidad de compras
# ════════════════════════════════════════════════════════════════════
@dataclass
class LoteInventario:
    fecha: date
    moneda: MonedaInventario
    cantidad: Decimal
    costo_unitario: Decimal
    id: str = field(default_factory=_nuevo_uuid)
    cantidad_consumida: Decimal = Decimal("0")
    cantidad_disponible: Optional[Decimal] = None
    estado: EstadoLote = "ABIERTO"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        self.moneda = _validar_moneda(self.moneda)
        if self.cantidad_disponible is None:
            self.cantidad_disponible = self.cantidad - self.cantidad_consumida

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fecha": self.fecha.isoformat() if isinstance(self.fecha, date) else self.fecha,
            "moneda": self.moneda,
            "cantidad": float(self.cantidad),
            "cantidad_consumida": float(self.cantidad_consumida),
            "cantidad_disponible": float(self.cantidad_disponible),
            "costo_unitario": float(self.costo_unitario),
            "estado": self.estado,
            **({"created_at": self.created_at.isoformat()} if self.created_at else {}),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LoteInventario":
        return cls(
            id=data.get("id", _nuevo_uuid()),
            fecha=data["fecha"],
            moneda=data["moneda"],
            cantidad=Decimal(str(data["cantidad"])),
            cantidad_consumida=Decimal(str(data.get("cantidad_consumida", 0) or 0)),
            cantidad_disponible=Decimal(str(data["cantidad_disponible"])) if data.get("cantidad_disponible") is not None else None,
            costo_unitario=Decimal(str(data["costo_unitario"])),
            estado=data.get("estado", "ABIERTO"),
            created_at=data.get("created_at"),
        )


# ════════════════════════════════════════════════════════════════════
# MODELO 4: UtilidadOperacion
# Utilidad real calculada con CPP del inventario (no tasa Binance)
# ════════════════════════════════════════════════════════════════════
@dataclass
class UtilidadOperacion:
    fecha: date
    referencia_operacion: str
    moneda: MonedaInventario
    cantidad: Decimal
    id: str = field(default_factory=_nuevo_uuid)
    precio_venta: Optional[Decimal] = None
    costo_promedio_aplicado: Optional[Decimal] = None
    ingreso: Optional[Decimal] = None
    costo: Optional[Decimal] = None
    utilidad_bruta: Optional[Decimal] = None
    comisiones: Decimal = Decimal("0")
    utilidad_neta: Optional[Decimal] = None
    estado: EstadoUtilidad = "PENDIENTE"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        self.moneda = _validar_moneda(self.moneda)

    def to_dict(self) -> dict:
        def _f(v):
            return float(v) if v is not None else None

        d = {
            "id": self.id,
            "fecha": self.fecha.isoformat() if isinstance(self.fecha, date) else self.fecha,
            "referencia_operacion": self.referencia_operacion,
            "moneda": self.moneda,
            "cantidad": float(self.cantidad),
            "precio_venta": _f(self.precio_venta),
            "costo_promedio_aplicado": _f(self.costo_promedio_aplicado),
            "ingreso": _f(self.ingreso),
            "costo": _f(self.costo),
            "utilidad_bruta": _f(self.utilidad_bruta),
            "comisiones": float(self.comisiones),
            "utilidad_neta": _f(self.utilidad_neta),
            "estado": self.estado,
        }
        if self.created_at:
            d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "UtilidadOperacion":
        def _dec(v):
            return Decimal(str(v)) if v is not None else None

        return cls(
            id=data.get("id", _nuevo_uuid()),
            fecha=data["fecha"],
            referencia_operacion=data["referencia_operacion"],
            moneda=data["moneda"],
            cantidad=Decimal(str(data["cantidad"])),
            precio_venta=_dec(data.get("precio_venta")),
            costo_promedio_aplicado=_dec(data.get("costo_promedio_aplicado")),
            ingreso=_dec(data.get("ingreso")),
            costo=_dec(data.get("costo")),
            utilidad_bruta=_dec(data.get("utilidad_bruta")),
            comisiones=_dec(data.get("comisiones", 0)) or Decimal("0"),
            utilidad_neta=_dec(data.get("utilidad_neta")),
            estado=data.get("estado", "PENDIENTE"),
            created_at=data.get("created_at"),
        )


# ════════════════════════════════════════════════════════════════════
# MODELO 5: OperacionComponente
# Descompone una operación de gsa_operaciones en componentes
# de inventario individuales
# ════════════════════════════════════════════════════════════════════
@dataclass
class OperacionComponente:
    operacion_id: str
    tipo_componente: str
    moneda: MonedaInventario
    cantidad: Decimal
    id: str = field(default_factory=_nuevo_uuid)
    secuencia: int = 1
    ingreso: Optional[Decimal] = None
    costo: Optional[Decimal] = None
    utilidad: Optional[Decimal] = None
    estado: EstadoComponente = "PENDIENTE"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        self.moneda = _validar_moneda(self.moneda)

    def to_dict(self) -> dict:
        def _f(v):
            return float(v) if v is not None else None

        d = {
            "id": self.id,
            "operacion_id": self.operacion_id,
            "secuencia": self.secuencia,
            "tipo_componente": self.tipo_componente,
            "moneda": self.moneda,
            "cantidad": float(self.cantidad),
            "ingreso": _f(self.ingreso),
            "costo": _f(self.costo),
            "utilidad": _f(self.utilidad),
            "estado": self.estado,
        }
        if self.created_at:
            d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "OperacionComponente":
        def _dec(v):
            return Decimal(str(v)) if v is not None else None

        return cls(
            id=data.get("id", _nuevo_uuid()),
            operacion_id=data["operacion_id"],
            secuencia=data.get("secuencia", 1),
            tipo_componente=data["tipo_componente"],
            moneda=data["moneda"],
            cantidad=Decimal(str(data["cantidad"])),
            ingreso=_dec(data.get("ingreso")),
            costo=_dec(data.get("costo")),
            utilidad=_dec(data.get("utilidad")),
            estado=data.get("estado", "PENDIENTE"),
            created_at=data.get("created_at"),
        )
