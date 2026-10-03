"""
Experimento de clasificación: compara reglas, LLM e híbrido sobre el conjunto de correos etiquetados a mano
(logismart/datos/correos_etiquetados.json, 32 correos).

Métricas: exactitud (categoría y prioridad), matriz de confusión por categoría, latencia promedio.
"""
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .esquema import CATEGORIAS_VALIDAS
from .hibrido import ClasificadorHibrido
from .llm import ClienteOllama, ErrorLLM
from .reglas import clasificar_por_reglas

RUTA_DATASET = Path(__file__).resolve().parent.parent / "datos" / "correos_etiquetados.json"


def cargar_dataset(ruta: Path = RUTA_DATASET) -> List[Dict]:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _matriz_vacia() -> Dict[str, Dict[str, int]]:
    return {real: {pred: 0 for pred in CATEGORIAS_VALIDAS} for real in CATEGORIAS_VALIDAS}


def _evaluar(nombre: str, fn: Callable[[Dict], Dict], dataset: List[Dict], progreso=None) -> Dict:
    matriz = _matriz_vacia()
    aciertos_cat = aciertos_pri = 0
    latencias, errores, fallos = [], [], 0
    for i, correo in enumerate(dataset, 1):
        inicio = time.perf_counter()
        try:
            pred = fn(correo)
        except ErrorLLM as exc:
            fallos += 1
            errores.append({"id": correo["id"], "error": str(exc)})
            if progreso:
                progreso(nombre, i, len(dataset))
            continue
        latencias.append((time.perf_counter() - inicio) * 1000)
        matriz[correo["categoria"]][pred["categoria"]] += 1
        if pred["categoria"] == correo["categoria"]:
            aciertos_cat += 1
        else:
            errores.append({"id": correo["id"], "asunto": correo["asunto"], "real": correo["categoria"],
                            "predicho": pred["categoria"]})
        if pred["prioridad"] == correo["prioridad"]:
            aciertos_pri += 1
        if progreso:
            progreso(nombre, i, len(dataset))
    n = len(dataset) - fallos
    return {
        "metodo": nombre, "n": n, "fallos_llm": fallos,
        "exactitud_categoria": round(aciertos_cat / n, 3) if n else 0,
        "exactitud_prioridad": round(aciertos_pri / n, 3) if n else 0,
        "latencia_promedio_ms": round(sum(latencias) / len(latencias), 1) if latencias else 0,
        "matriz_confusion": matriz, "errores": errores,
    }


def evaluar_clasificadores(llm: Optional[ClienteOllama] = None, incluir_llm: bool = True,
                           dataset: Optional[List[Dict]] = None, progreso=None) -> Dict:
    dataset = dataset or cargar_dataset()
    llm = llm or ClienteOllama()
    resultados = {"reglas": _evaluar("reglas", lambda c: clasificar_por_reglas(c["asunto"], c["cuerpo"]), dataset, progreso)}
    if incluir_llm:
        ok, msg = llm.disponible()
        if ok:
            resultados["llm"] = _evaluar(
                "llm", lambda c: llm.clasificar(c["asunto"], c["cuerpo"], c["remitente"])[0].model_dump(), dataset, progreso)
            hib = ClasificadorHibrido(llm=llm, repos=None)
            resultados["hibrido"] = _evaluar(
                "hibrido", lambda c: hib.clasificar(c["asunto"], c["cuerpo"], c["remitente"]), dataset, progreso)
        else:
            resultados["aviso"] = f"LLM no evaluado: {msg}"
    return {"total_correos": len(dataset), "modelo": llm.modelo, "resultados": resultados}


def reporte_evaluacion_texto(reporte: Dict) -> str:
    L = [f"EXPERIMENTO DE CLASIFICACIÓN  ({reporte['total_correos']} correos etiquetados a mano, modelo {reporte['modelo']})",
         "=" * 90, f"{'Método':<10}{'N':>4}{'Exact. categoría':>18}{'Exact. prioridad':>18}{'Latencia ms':>14}{'Fallos LLM':>12}",
         "-" * 90]
    for nombre, r in reporte["resultados"].items():
        if nombre == "aviso":
            continue
        L.append(f"{nombre:<10}{r['n']:>4}{r['exactitud_categoria']:>18.1%}{r['exactitud_prioridad']:>18.1%}"
                 f"{r['latencia_promedio_ms']:>14.1f}{r['fallos_llm']:>12}")
    if "aviso" in reporte["resultados"]:
        L.append(f"\n{reporte['resultados']['aviso']}")
    abrev = {c: c[:6] for c in CATEGORIAS_VALIDAS}
    for nombre, r in reporte["resultados"].items():
        if nombre == "aviso":
            continue
        L += ["", f"Matriz de confusión - {nombre} (filas = real, columnas = predicho)",
              f"{'':<22}" + "".join(f"{abrev[c]:>8}" for c in CATEGORIAS_VALIDAS)]
        for real in CATEGORIAS_VALIDAS:
            L.append(f"{real:<22}" + "".join(f"{r['matriz_confusion'][real][p]:>8}" for p in CATEGORIAS_VALIDAS))
        if r["errores"]:
            L.append("  Errores:")
            for e in r["errores"][:15]:
                if "real" in e:
                    L.append(f"    #{e['id']:<3} {e['asunto'][:40]:<40} real={e['real']}  predicho={e['predicho']}")
                else:
                    L.append(f"    #{e['id']:<3} ERROR LLM: {e['error'][:70]}")
    return "\n".join(L)
