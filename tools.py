from typing import Any

from langchain_core.tools import BaseTool, tool

from database import (
    consultar_cliente_por_id,
    consultar_clientes,
    consultar_pedido,
    consultar_pedidos,
    total_pedido,
)


@tool
async def buscar_cliente(nombre: str) -> dict[str, Any]:
    """Busca clientes en la base de datos de la tienda por nombre o apellido.

    Usar SIEMPRE esta herramienta primero cuando el usuario menciona a un cliente por su
    nombre, porque las demás herramientas necesitan el cliente_id numérico.

    Args:
        nombre: nombre, apellido o nombre completo del cliente. Acepta coincidencias
            parciales y no distingue mayúsculas ni tildes. Ejemplo: "Laura Méndez" o "Gómez".

    Returns:
        - Si hay una sola coincidencia: los datos del cliente (cliente_id, nombre, ciudad, email).
        - Si hay varias coincidencias: "ambiguo" en true y la lista de candidatos. En ese caso
          NO elegir uno al azar: pedir al usuario que aclare cuál es, por ejemplo por la ciudad.
        - Si no hay coincidencias: un campo "error" con una sugerencia.
    """
    coincidencias = await consultar_clientes(nombre)
    if not coincidencias:
        return {
            "error": f"No existe ningún cliente que coincida con '{nombre}'.",
            "sugerencia": "Verificar la ortografía o pedir al usuario el nombre completo o el ID del cliente.",
        }
    if len(coincidencias) > 1:
        return {
            "ambiguo": True,
            "coincidencias": coincidencias,
            "sugerencia": "Pedir al usuario que indique cuál de estos clientes es antes de continuar.",
        }
    return dict(coincidencias[0])


@tool
async def buscar_pedidos(cliente_id: int) -> dict[str, Any]:
    """Obtiene el historial de pedidos de un cliente: cantidad de pedidos, total gastado y
    la lista de pedidos ordenada del más antiguo al más reciente.

    Usar cuando el usuario pregunta cuántos pedidos tiene un cliente, cuánto gastó, o cuál fue
    su primer o último pedido. El último pedido es el último elemento de la lista "pedidos".
    Los pedidos cancelados se listan pero NO suman al total gastado.

    Args:
        cliente_id: ID numérico del cliente, por ejemplo 101. Si solo se conoce el nombre,
            obtenerlo antes con buscar_cliente.

    Returns:
        cliente_id, cantidad_pedidos, total_gastado (en pesos argentinos, sin cancelados) y
        pedidos (pedido_id, fecha, estado, total). Si el cliente no existe, un campo "error".
    """
    cliente = await consultar_cliente_por_id(cliente_id)
    if cliente is None:
        return {
            "error": f"No existe un cliente con ID {cliente_id}.",
            "sugerencia": "Usar buscar_cliente con el nombre para obtener el ID correcto.",
        }
    pedidos = await consultar_pedidos(cliente_id)
    resumen = [
        {"pedido_id": p["pedido_id"], "fecha": p["fecha"], "estado": p["estado"], "total": total_pedido(p)}
        for p in pedidos
    ]
    return {
        "cliente_id": cliente_id,
        "cliente": cliente["nombre"],
        "cantidad_pedidos": len(pedidos),
        "total_gastado": sum(p["total"] for p in resumen if p["estado"] != "cancelado"),
        "moneda": "ARS",
        "pedidos": resumen,
    }


@tool
async def obtener_detalle_pedido(pedido_id: str) -> dict[str, Any]:
    """Obtiene el detalle completo de un pedido: productos, cantidades, precios unitarios,
    estado y total.

    Usar cuando el usuario pregunta qué productos tenía un pedido o pide el detalle de uno.
    Requiere el pedido_id, que se obtiene con buscar_pedidos.

    La base de pedidos puede responder con un error temporal de timeout. Si eso ocurre,
    volver a llamar a esta herramienta con el mismo pedido_id una vez más antes de rendirse.

    Args:
        pedido_id: identificador del pedido con formato "P-" seguido de números, por ejemplo "P-1015".

    Returns:
        pedido_id, cliente_id, fecha, estado, items y total. Si el pedido no existe, un campo "error".
    """
    pedido = await consultar_pedido(pedido_id)
    if pedido is None:
        return {
            "error": f"No existe el pedido {pedido_id}.",
            "sugerencia": "Usar buscar_pedidos para obtener los pedido_id válidos del cliente.",
        }
    return {**pedido, "total": total_pedido(pedido), "moneda": "ARS"}


TOOLS: list[BaseTool] = [buscar_cliente, buscar_pedidos, obtener_detalle_pedido]
