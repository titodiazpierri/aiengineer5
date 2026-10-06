import argparse
import asyncio

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent import construir_grafo, ejecutar_turno
from config import CHECKPOINT_DB, LLM_MODEL, LLM_PROVIDER, RECURSION_LIMIT, verificar_credenciales
from traza import TrazaReAct


async def chat(thread_id: str) -> None:
    verificar_credenciales()
    traza = TrazaReAct(LLM_PROVIDER, LLM_MODEL, RECURSION_LIMIT)
    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        grafo = construir_grafo(checkpointer)
        estado = await grafo.aget_state({"configurable": {"thread_id": thread_id}})
        previos = len(estado.values.get("messages", [])) if estado.values else 0
        print(f"Sesión '{thread_id}' ({previos} mensajes previos). Escribí 'salir' para terminar.")
        while True:
            mensaje = (await asyncio.to_thread(input, "\nVos: ")).strip()
            if mensaje.lower() in {"salir", "exit", "quit"}:
                break
            if mensaje:
                await ejecutar_turno(grafo, thread_id, mensaje, traza)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chat con el agente con memoria persistente")
    parser.add_argument("--thread", default="sesion-cli", help="thread_id de la conversación")
    asyncio.run(chat(parser.parse_args().thread))
