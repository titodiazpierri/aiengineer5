import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
CHECKPOINT_DB = str(BASE_DIR / os.getenv("CHECKPOINT_DB", "checkpoints.sqlite"))
TRAZAS_DIR = BASE_DIR / "trazas"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
MODELOS_POR_DEFECTO: dict[str, str] = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-4-5",
}
LLM_MODEL = os.getenv("LLM_MODEL") or MODELOS_POR_DEFECTO.get(LLM_PROVIDER, "")

RECURSION_LIMIT = 10
MAX_TOKENS_CONTEXTO = 4000


def crear_llm() -> BaseChatModel:
    parametros: dict = {"model": LLM_MODEL, "temperature": 0, "max_tokens": 1024, "timeout": 60, "max_retries": 2}
    if LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(**parametros)
    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(**parametros)
    raise ValueError(f"LLM_PROVIDER inválido: {LLM_PROVIDER}. Usar openai o anthropic")


def verificar_credenciales() -> None:
    variable = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(LLM_PROVIDER)
    if variable and not os.getenv(variable):
        raise RuntimeError(f"Falta {variable}. Copiá .env.example a .env y completá la clave.")
