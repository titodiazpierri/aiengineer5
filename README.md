# Agente ReAct con LangGraph y memoria persistente

Agente de atención al cliente que razona en ciclos (ReAct) sobre una base de datos simulada de clientes y pedidos. Decide por sí mismo qué herramientas usar, encadena varias llamadas para llegar a una respuesta, reintenta ante errores, pide aclaraciones cuando la información es ambigua y recuerda la conversación entre ejecuciones gracias a un checkpointer SQLite.

## Estructura

| Archivo | Contenido |
|---|---|
| `agent.py` | Estado `AgentState(MessagesState)`, nodos, `StateGraph` con `tools_condition` y ejecución de turnos |
| `tools.py` | Herramientas `@tool` asíncronas con docstrings descriptivos |
| `database.py` | Base de datos simulada de clientes y pedidos, con consultas asíncronas |
| `config.py` | Variables de entorno, LLM, `recursion_limit` y ruta del checkpointer |
| `traza.py` | Registro de la traza ReAct en `.json` y `.log` |
| `demo.py` | Prueba de ejecución con tres escenarios; genera la traza |
| `chat.py` | Chat interactivo por consola con `thread_id` |
| `trazas/` | Traza de ejecución generada por `demo.py` |

## Arquitectura del grafo

```
START → agente ──tools_condition──→ tools ──→ agente
                └──────────────────→ END
```

- **Estado**: `AgentState` hereda de `MessagesState`, cuya lista `messages` usa el reducer `add_messages`, que agrega cada mensaje nuevo al historial en lugar de reemplazarlo. Suma el campo `pasos_modelo`, acumulado con el reducer `operator.add`.
- **Nodo `agente`**: invoca el LLM con `llm.bind_tools(TOOLS)` de forma asíncrona (`ainvoke`).
- **Nodo `tools`**: `ToolNode` ejecuta las herramientas que pidió el modelo. Si una herramienta lanza una excepción, la convierte en un mensaje de error para el modelo en lugar de cortar la ejecución.
- **Arista condicional `tools_condition`**: si la respuesta del modelo contiene llamadas a herramientas, va a `tools`; si no, termina. No hay rutas manuales con `if/else`: el modelo decide.
- **Arista `tools → agente`**: cierra el ciclo ReAct, para que el modelo vea el resultado y decida si necesita otra herramienta o ya puede responder.

### Control del contexto y de los costos

- `recursion_limit = 10` en cada invocación. Si el agente entra en un bucle, LangGraph lanza `GraphRecursionError`, que se captura y se registra en la traza.
- `trim_messages` recorta el historial que recibe el modelo a los últimos 4000 tokens aproximados, empezando siempre en un mensaje del usuario para no separar una llamada a herramienta de su resultado. El historial completo se conserva en el checkpointer; solo se recorta lo que se envía al LLM.

## Herramientas

| Herramienta | Entrada | Devuelve |
|---|---|---|
| `buscar_cliente` | `nombre: str` | Datos del cliente, lista de candidatos si es ambiguo, o error con sugerencia |
| `buscar_pedidos` | `cliente_id: int` | Cantidad de pedidos, total gastado y lista de pedidos ordenada por fecha |
| `obtener_detalle_pedido` | `pedido_id: str` | Productos, cantidades, precios y total del pedido |

Cada docstring explica cuándo usar la herramienta, qué parámetros espera con ejemplos y qué devuelve en cada caso, porque es lo único que el modelo ve para decidir.

### Ciclo de retorno

- **Error con sugerencia**: si un cliente o pedido no existe, la herramienta devuelve `error` y `sugerencia` (por ejemplo, usar `buscar_cliente` para obtener el ID correcto), y el agente corrige el rumbo.
- **Información ambigua**: si un nombre coincide con varios clientes, la herramienta devuelve `ambiguo: true` con los candidatos y el agente le pide al usuario que aclare.
- **Error temporal**: con `SIMULAR_FALLAS=true`, la primera consulta de cada pedido en `obtener_detalle_pedido` falla con un timeout simulado. El `ToolNode` le devuelve el error al modelo y este reintenta la llamada.

## Persistencia

El grafo se compila con `AsyncSqliteSaver`, la versión asíncrona de `SqliteSaver` de `langgraph-checkpoint-sqlite`. Cada paso del grafo guarda un checkpoint en `checkpoints.sqlite` asociado al `thread_id`:

```python
async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
    grafo = construir_grafo(checkpointer)
    config = {"configurable": {"thread_id": "demo-multipaso"}, "recursion_limit": 10}
    await grafo.ainvoke({"messages": [HumanMessage("...")]}, config)
```

Con el mismo `thread_id` el agente recupera toda la conversación anterior, incluso después de cerrar el programa. Con un `thread_id` distinto empieza una sesión nueva.

## Cómo levantar el entorno

Requiere Python 3.12 o superior.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

En Windows: `py -3.12 -m venv .venv`, `.venv\Scripts\activate` y `copy .env.example .env`.

### Variables de entorno

| Variable | Descripción |
|---|---|
| `LLM_PROVIDER` | `openai` o `anthropic` |
| `OPENAI_API_KEY` | API key de OpenAI |
| `ANTHROPIC_API_KEY` | API key de Anthropic |
| `LLM_MODEL` | Opcional. Por defecto `gpt-4.1-mini` o `claude-haiku-4-5` |
| `CHECKPOINT_DB` | Opcional. Archivo SQLite de checkpoints. Por defecto `checkpoints.sqlite` |
| `SIMULAR_FALLAS` | Opcional. `true` simula un timeout en la primera consulta de cada pedido |

`.env` y los archivos `.sqlite` están en `.gitignore`: ni las credenciales ni las conversaciones se suben al repositorio.

## Ejecución

Prueba completa, que genera la traza en `trazas/traza_react.json` y `trazas/traza_react.log`:

```bash
python demo.py
```

Chat interactivo con memoria:

```bash
python chat.py --thread mi-sesion
```

Si se cierra el chat y se vuelve a abrir con el mismo `--thread`, el agente sigue la conversación donde quedó.

## Escenarios de la prueba

| # | Escenario | thread_id | Qué demuestra |
|---|---|---|---|
| 1 | "¿Cuántos pedidos tuvo la clienta Laura Méndez y cuál fue el total que gastó?" y luego "¿Y el último? ¿Qué productos tenía?" | `demo-multipaso` | Razonamiento multi-paso (`buscar_cliente` → `buscar_pedidos`), memoria dentro de la sesión y reintento ante un error temporal |
| 2 | "¿Cuánto gastó el cliente Gómez?" y luego "El de Córdoba." | `demo-aclaracion` | Ciclo de retorno: el agente detecta la ambigüedad, pide aclaración y continúa |
| 3 | "Recordame de qué clienta estábamos hablando..." | `demo-multipaso` | Persistencia: con una conexión y un grafo nuevos, la conversación se recupera desde SQLite |

Al final, `demo.py` imprime una verificación con la cantidad de llamadas a herramientas por escenario y confirma que el primer turno usó al menos dos herramientas.

## Ejemplo de traza

Formato del log generado en `trazas/traza_react.log`:

```
[thread_id=demo-multipaso] Usuario: "¿Cuántos pedidos tuvo la clienta Laura Méndez y cuál fue el total que gastó?"
→ El agente decide usar la herramienta: buscar_cliente(nombre='Laura Méndez')
→ La herramienta devuelve: {"cliente_id": 101, "nombre": "Laura Méndez", "ciudad": "Rosario", ...}
→ El agente decide usar la herramienta: buscar_pedidos(cliente_id=101)
→ La herramienta devuelve: {"cliente_id": 101, "cantidad_pedidos": 3, "total_gastado": 569000, ...}
→ El agente razona: ya tiene los datos necesarios → responde.
Respuesta: "..."
```

La traza completa de una ejecución real está en `trazas/traza_react.log` y, en formato estructurado, en `trazas/traza_react.json`.
