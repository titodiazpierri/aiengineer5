import json
import operator
from typing import Annotated, Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, trim_messages
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from config import MAX_TOKENS_CONTEXTO, RECURSION_LIMIT, crear_llm
from tools import TOOLS
from traza import Evento, Turno, TrazaReAct

SYSTEM_PROMPT = """Sos un asistente de atención al cliente de una tienda de tecnología con acceso a su base de datos mediante herramientas.

Forma de trabajar:
1. Decidí por tu cuenta qué herramienta necesitás según la pregunta. Podés encadenar varias: por ejemplo, buscar_cliente para obtener el cliente_id y después buscar_pedidos.
2. Antes de responder, verificá que tenés todos los datos. Si falta información, llamá a otra herramienta.
3. Si una herramienta devuelve un error temporal, reintentá la misma llamada una vez. Si devuelve un error con "sugerencia", seguí la sugerencia.
4. Si un nombre coincide con varios clientes, no elijas uno: preguntale al usuario cuál es, mostrando las opciones.
5. Usá el historial de la conversación: si el usuario dice "el último" o "ese cliente", se refiere a lo que ya hablaron.
6. No inventes datos. Respondé en español, de forma breve, con montos en pesos argentinos con separador de miles (por ejemplo $14.500)."""


class AgentState(MessagesState):
    pasos_modelo: Annotated[int, operator.add]


def manejar_error_herramienta(error: Exception) -> str:
    return f"Error al ejecutar la herramienta ({type(error).__name__}): {error} Si es un error temporal, reintentar la misma llamada una vez."


def recortar_historial(mensajes: list) -> list:
    return trim_messages(
        mensajes,
        max_tokens=MAX_TOKENS_CONTEXTO,
        token_counter=count_tokens_approximately,
        strategy="last",
        start_on="human",
        include_system=False,
        allow_partial=False,
    )


def construir_grafo(checkpointer: BaseCheckpointSaver, llm: BaseChatModel | None = None) -> CompiledStateGraph:
    llm_con_herramientas = (llm or crear_llm()).bind_tools(TOOLS)

    async def agente(state: AgentState) -> dict[str, Any]:
        historial = recortar_historial(state["messages"])
        respuesta = await llm_con_herramientas.ainvoke([SystemMessage(SYSTEM_PROMPT), *historial])
        return {"messages": [respuesta], "pasos_modelo": 1}

    builder = StateGraph(AgentState)
    builder.add_node("agente", agente)
    builder.add_node("tools", ToolNode(TOOLS, handle_tool_errors=manejar_error_herramienta))
    builder.add_edge(START, "agente")
    builder.add_conditional_edges("agente", tools_condition)
    builder.add_edge("tools", "agente")
    return builder.compile(checkpointer=checkpointer)


def formatear_argumentos(argumentos: dict[str, Any]) -> str:
    return ", ".join(f"{clave}={valor!r}" for clave, valor in argumentos.items())


def contenido_herramienta(mensaje: ToolMessage) -> Any:
    try:
        return json.loads(mensaje.content)
    except (TypeError, ValueError):
        return mensaje.content


async def ejecutar_turno(grafo: CompiledStateGraph, thread_id: str, mensaje: str, traza: TrazaReAct) -> Turno:
    turno = Turno(thread_id=thread_id, mensaje_usuario=mensaje)
    turno.eventos.append(Evento(tipo="usuario", contenido=mensaje))
    traza.registrar(f"\n[thread_id={thread_id}] Usuario: \"{mensaje}\"")

    config: RunnableConfig = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    try:
        async for actualizacion in grafo.astream({"messages": [HumanMessage(mensaje)]}, config, stream_mode="updates"):
            for nodo, cambios in actualizacion.items():
                for msg in (cambios or {}).get("messages", []):
                    registrar_mensaje(nodo, msg, turno, traza)
    except GraphRecursionError:
        turno.eventos.append(Evento(tipo="limite_recursion", contenido=f"Se alcanzó el límite de {RECURSION_LIMIT} pasos"))
        traza.registrar(f"→ Se alcanzó el recursion_limit ({RECURSION_LIMIT}). Ejecución detenida para evitar un bucle.")
    return turno


def registrar_mensaje(nodo: str, msg: Any, turno: Turno, traza: TrazaReAct) -> None:
    if isinstance(msg, AIMessage):
        turno.pasos_modelo += 1
        if msg.tool_calls:
            for llamada in msg.tool_calls:
                turno.llamadas_herramientas += 1
                turno.eventos.append(Evento(
                    tipo="llamada_herramienta", contenido=None,
                    herramienta=llamada["name"], argumentos=llamada["args"],
                ))
                traza.registrar(f"→ El agente decide usar la herramienta: {llamada['name']}({formatear_argumentos(llamada['args'])})")
        else:
            turno.eventos.append(Evento(tipo="respuesta", contenido=msg.text))
            traza.registrar("→ El agente razona: ya tiene los datos necesarios → responde.")
            traza.registrar(f"Respuesta: \"{msg.text}\"")
    elif isinstance(msg, ToolMessage):
        contenido = contenido_herramienta(msg)
        es_error = msg.status == "error" or (isinstance(contenido, dict) and "error" in contenido)
        turno.eventos.append(Evento(
            tipo="error_herramienta" if es_error else "resultado_herramienta",
            contenido=contenido, herramienta=msg.name,
        ))
        etiqueta = "La herramienta devuelve un ERROR" if es_error else "La herramienta devuelve"
        texto = json.dumps(contenido, ensure_ascii=False) if isinstance(contenido, (dict, list)) else str(contenido)
        traza.registrar(f"→ {etiqueta}: {texto}")
