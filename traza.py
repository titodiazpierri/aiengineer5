import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

TipoEvento = Literal["usuario", "llamada_herramienta", "resultado_herramienta", "error_herramienta", "respuesta", "limite_recursion"]


@dataclass
class Evento:
    tipo: TipoEvento
    contenido: Any
    herramienta: str | None = None
    argumentos: dict[str, Any] | None = None


@dataclass
class Turno:
    thread_id: str
    mensaje_usuario: str
    eventos: list[Evento] = field(default_factory=list)
    llamadas_herramientas: int = 0
    pasos_modelo: int = 0


@dataclass
class Escenario:
    nombre: str
    objetivo: str
    turnos: list[Turno] = field(default_factory=list)


class TrazaReAct:
    def __init__(self, proveedor: str, modelo: str, recursion_limit: int) -> None:
        self.metadatos: dict[str, Any] = {
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "proveedor": proveedor,
            "modelo": modelo,
            "recursion_limit": recursion_limit,
        }
        self.escenarios: list[Escenario] = []
        self.lineas: list[str] = []

    def nuevo_escenario(self, nombre: str, objetivo: str) -> Escenario:
        escenario = Escenario(nombre=nombre, objetivo=objetivo)
        self.escenarios.append(escenario)
        self.registrar("")
        self.registrar("=" * 80)
        self.registrar(f"ESCENARIO: {nombre}")
        self.registrar(f"Objetivo: {objetivo}")
        self.registrar("=" * 80)
        return escenario

    def registrar(self, linea: str) -> None:
        self.lineas.append(linea)
        print(linea)

    def guardar(self, directorio: Path, nombre: str = "traza_react") -> tuple[Path, Path]:
        directorio.mkdir(exist_ok=True)
        ruta_json = directorio / f"{nombre}.json"
        ruta_log = directorio / f"{nombre}.log"
        datos = {"metadatos": self.metadatos, "escenarios": [asdict(e) for e in self.escenarios]}
        ruta_json.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        ruta_log.write_text("\n".join(self.lineas) + "\n", encoding="utf-8")
        return ruta_json, ruta_log
