import asyncio
import logging
import sqlite3

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent import construir_grafo, ejecutar_turno
from config import CHECKPOINT_DB, LLM_MODEL, LLM_PROVIDER, RECURSION_LIMIT, TRAZAS_DIR, verificar_credenciales
from traza import Escenario, TrazaReAct

THREAD_MULTIPASO = "demo-multipaso"
THREAD_ACLARACION = "demo-aclaracion"


async def limpiar_threads(checkpointer: AsyncSqliteSaver, *thread_ids: str) -> None:
    await checkpointer.setup()
    for thread_id in thread_ids:
        await checkpointer.adelete_thread(thread_id)


def contar_checkpoints(thread_id: str) -> int:
    with sqlite3.connect(CHECKPOINT_DB) as conexion:
        return conexion.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,)).fetchone()[0]


def verificar(traza: TrazaReAct) -> None:
    traza.registrar("")
    traza.registrar("=" * 80)
    traza.registrar("VERIFICACIÓN")
    traza.registrar("=" * 80)
    for escenario in traza.escenarios:
        total = sum(t.llamadas_herramientas for t in escenario.turnos)
        errores = sum(1 for t in escenario.turnos for e in t.eventos if e.tipo == "error_herramienta")
        traza.registrar(f"{escenario.nombre}: {total} llamadas a herramientas, {errores} errores manejados, {len(escenario.turnos)} turnos")
    primer = traza.escenarios[0].turnos[0]
    estado = "OK" if primer.llamadas_herramientas >= 2 else "REVISAR"
    traza.registrar(f"Razonamiento multi-paso (≥2 herramientas en el primer turno): {primer.llamadas_herramientas} → {estado}")


async def main() -> None:
    verificar_credenciales()
    traza = TrazaReAct(LLM_PROVIDER, LLM_MODEL, RECURSION_LIMIT)

    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        await limpiar_threads(checkpointer, THREAD_MULTIPASO, THREAD_ACLARACION)
        grafo = construir_grafo(checkpointer)

        escenario: Escenario = traza.nuevo_escenario(
            "1. Razonamiento multi-paso y memoria",
            "El agente encadena buscar_cliente y buscar_pedidos; en el segundo turno usa el contexto previo y reintenta ante un error temporal.",
        )
        escenario.turnos.append(await ejecutar_turno(grafo, THREAD_MULTIPASO, "¿Cuántos pedidos tuvo la clienta Laura Méndez y cuál fue el total que gastó?", traza))
        escenario.turnos.append(await ejecutar_turno(grafo, THREAD_MULTIPASO, "¿Y el último? ¿Qué productos tenía?", traza))

        escenario = traza.nuevo_escenario(
            "2. Ciclo de retorno ante información ambigua",
            "La herramienta devuelve varios clientes; el agente pide una aclaración y continúa con la respuesta del usuario.",
        )
        escenario.turnos.append(await ejecutar_turno(grafo, THREAD_ACLARACION, "¿Cuánto gastó el cliente Gómez?", traza))
        escenario.turnos.append(await ejecutar_turno(grafo, THREAD_ACLARACION, "El de Córdoba.", traza))

    traza.registrar(f"\nConexión a SQLite cerrada. Checkpoints guardados para '{THREAD_MULTIPASO}': {contar_checkpoints(THREAD_MULTIPASO)}")

    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        grafo = construir_grafo(checkpointer)
        escenario = traza.nuevo_escenario(
            "3. Persistencia con SqliteSaver",
            "Con una conexión y un grafo nuevos, el mismo thread_id recupera la conversación guardada en checkpoints.sqlite.",
        )
        escenario.turnos.append(await ejecutar_turno(grafo, THREAD_MULTIPASO, "Recordame de qué clienta estábamos hablando y cuál era el pedido que estaba en camino.", traza))

    verificar(traza)
    ruta_json, ruta_log = traza.guardar(TRAZAS_DIR)
    print(f"\nTraza guardada en {ruta_json.name} y {ruta_log.name} (carpeta {TRAZAS_DIR.name}/)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
