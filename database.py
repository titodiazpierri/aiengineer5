import asyncio
import os
import unicodedata
from typing import TypedDict


class Cliente(TypedDict):
    cliente_id: int
    nombre: str
    ciudad: str
    email: str


class Item(TypedDict):
    producto: str
    cantidad: int
    precio_unitario: int


class Pedido(TypedDict):
    pedido_id: str
    cliente_id: int
    fecha: str
    estado: str
    items: list[Item]


CLIENTES: list[Cliente] = [
    {"cliente_id": 101, "nombre": "Laura Méndez", "ciudad": "Rosario", "email": "laura.mendez@correo.com"},
    {"cliente_id": 102, "nombre": "Martín Gómez", "ciudad": "Córdoba", "email": "martin.gomez@correo.com"},
    {"cliente_id": 103, "nombre": "Sofía Gómez", "ciudad": "Mendoza", "email": "sofia.gomez@correo.com"},
    {"cliente_id": 104, "nombre": "Diego Paz", "ciudad": "Buenos Aires", "email": "diego.paz@correo.com"},
]

PEDIDOS: list[Pedido] = [
    {"pedido_id": "P-1001", "cliente_id": 101, "fecha": "2026-07-14", "estado": "entregado",
     "items": [{"producto": "Teclado mecánico", "cantidad": 1, "precio_unitario": 85000}]},
    {"pedido_id": "P-1007", "cliente_id": 101, "fecha": "2026-08-22", "estado": "entregado",
     "items": [{"producto": "Mouse inalámbrico", "cantidad": 2, "precio_unitario": 21500},
               {"producto": "Pad de escritorio", "cantidad": 1, "precio_unitario": 12000}]},
    {"pedido_id": "P-1015", "cliente_id": 101, "fecha": "2026-09-30", "estado": "en camino",
     "items": [{"producto": "Monitor 27 pulgadas", "cantidad": 1, "precio_unitario": 410000},
               {"producto": "Cable HDMI 2.1", "cantidad": 2, "precio_unitario": 9500}]},
    {"pedido_id": "P-1003", "cliente_id": 102, "fecha": "2026-07-20", "estado": "entregado",
     "items": [{"producto": "Auriculares", "cantidad": 1, "precio_unitario": 64000}]},
    {"pedido_id": "P-1011", "cliente_id": 102, "fecha": "2026-09-05", "estado": "cancelado",
     "items": [{"producto": "Webcam HD", "cantidad": 1, "precio_unitario": 48000}]},
    {"pedido_id": "P-1009", "cliente_id": 103, "fecha": "2026-08-30", "estado": "entregado",
     "items": [{"producto": "Silla ergonómica", "cantidad": 1, "precio_unitario": 290000}]},
]

SIMULAR_FALLAS = os.getenv("SIMULAR_FALLAS", "true").lower() == "true"
_pedidos_consultados: set[str] = set()


class BaseDeDatosNoDisponible(Exception):
    pass


def normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).strip()


def total_pedido(pedido: Pedido) -> int:
    return sum(item["cantidad"] * item["precio_unitario"] for item in pedido["items"])


async def consultar_clientes(nombre: str) -> list[Cliente]:
    await asyncio.sleep(0.05)
    buscado = normalizar(nombre)
    return [c for c in CLIENTES if buscado in normalizar(c["nombre"])]


async def consultar_cliente_por_id(cliente_id: int) -> Cliente | None:
    await asyncio.sleep(0.05)
    return next((c for c in CLIENTES if c["cliente_id"] == cliente_id), None)


async def consultar_pedidos(cliente_id: int) -> list[Pedido]:
    await asyncio.sleep(0.05)
    return sorted((p for p in PEDIDOS if p["cliente_id"] == cliente_id), key=lambda p: p["fecha"])


async def consultar_pedido(pedido_id: str) -> Pedido | None:
    await asyncio.sleep(0.05)
    pedido_id = pedido_id.strip().upper()
    if SIMULAR_FALLAS and pedido_id not in _pedidos_consultados:
        _pedidos_consultados.add(pedido_id)
        raise BaseDeDatosNoDisponible("Timeout al consultar la réplica de pedidos. Reintentar la consulta.")
    return next((p for p in PEDIDOS if p["pedido_id"] == pedido_id), None)
