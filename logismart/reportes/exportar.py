"""
Exportación de reportes a CSV, JSON y PDF.

El PDF se genera con un escritor mínimo en biblioteca estándar (texto, fuente Helvetica, varias páginas)
para no depender de bibliotecas externas.
"""
import csv
import json
import zlib
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional


# ---------------------------------------------------------------------------
def _serializar(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def aplanar(doc: Dict, prefijo: str = "") -> Dict:
    """Convierte documentos anidados en una fila plana para CSV: {'a': {'b': 1}} -> {'a.b': 1}."""
    fila = {}
    for k, v in doc.items():
        clave = f"{prefijo}{k}"
        if isinstance(v, dict):
            fila.update(aplanar(v, clave + "."))
        elif isinstance(v, list):
            fila[clave] = json.dumps(v, default=_serializar, ensure_ascii=False)
        else:
            fila[clave] = _serializar(v) if isinstance(v, (datetime, date)) else v
    return fila


def exportar_json(datos, ruta: str) -> str:
    Path(ruta).write_text(json.dumps(datos, default=_serializar, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def exportar_csv(docs: Iterable[Dict], ruta: str) -> str:
    filas = [aplanar(d) for d in docs]
    columnas: List[str] = []
    for f in filas:
        for c in f:
            if c not in columnas:
                columnas.append(c)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:       # BOM para que Excel lea acentos
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)
    return ruta


# ---------------------------------------------------------------------------
# PDF mínimo
# ---------------------------------------------------------------------------
_REEMPLAZOS = {"∧": " AND ", "∨": " OR ", "¬": "NOT ", "→": "->", "≡": "==", "—": "-", "–": "-", "“": '"', "”": '"',
               "‘": "'", "’": "'", "…": "...", "•": "-"}


def _pdf_texto(t: str) -> str:
    for a, b in _REEMPLAZOS.items():
        t = t.replace(a, b)
    t = t.encode("cp1252", errors="replace").decode("cp1252")
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def exportar_pdf(titulo: str, lineas: List[str], ruta: str, lineas_por_pagina: int = 58) -> str:
    """Genera un PDF de texto monoespaciado (Courier) con encabezado y numeración de páginas."""
    ancho, alto, margen, tam = 612, 792, 40, 9
    paginas = [lineas[i:i + lineas_por_pagina] for i in range(0, max(len(lineas), 1), lineas_por_pagina)] or [[]]
    objetos: List[bytes] = []

    def agregar(obj: bytes) -> int:
        objetos.append(obj)
        return len(objetos)

    fuente = agregar(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    fuente_b = agregar(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    ids_paginas = []
    paginas_idx = len(objetos) + 1 + 2 * len(paginas)   # el objeto /Pages se crea al final
    for n, bloque in enumerate(paginas, 1):
        contenido = [f"BT /F2 13 Tf {margen} {alto - margen} Td ({_pdf_texto(titulo)}) Tj ET",
                     f"BT /F1 8 Tf {ancho - margen - 120} {alto - margen} Td "
                     f"({_pdf_texto(f'Pagina {n}/{len(paginas)}  {datetime.now():%Y-%m-%d %H:%M}')}) Tj ET",
                     f"BT /F1 {tam} Tf {margen} {alto - margen - 24} Td {tam + 3} TL"]
        for linea in bloque:
            contenido.append(f"({_pdf_texto(linea[:110])}) Tj T*")
        contenido.append("ET")
        flujo = zlib.compress("\n".join(contenido).encode("cp1252", errors="replace"))
        id_contenido = agregar(b"<< /Length " + str(len(flujo)).encode() + b" /Filter /FlateDecode >>\nstream\n"
                               + flujo + b"\nendstream")
        id_pagina = agregar(f"<< /Type /Page /Parent {paginas_idx} 0 R /MediaBox [0 0 {ancho} {alto}] "
                            f"/Contents {id_contenido} 0 R /Resources << /Font << /F1 {fuente} 0 R /F2 {fuente_b} 0 R >> >> >>".encode())
        ids_paginas.append(id_pagina)
    kids = " ".join(f"{i} 0 R" for i in ids_paginas)
    id_pages = agregar(f"<< /Type /Pages /Kids [{kids}] /Count {len(ids_paginas)} >>".encode())
    assert id_pages == paginas_idx
    id_catalogo = agregar(f"<< /Type /Catalog /Pages {id_pages} 0 R >>".encode())

    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objetos, 1):
        offsets.append(len(salida))
        salida += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        salida += f"{off:010d} 00000 n \n".encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root {id_catalogo} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(ruta).write_bytes(salida)
    return ruta


# ---------------------------------------------------------------------------
def generar_reporte_completo(repos, servicio_riesgos, desde: Optional[datetime] = None,
                             hasta: Optional[datetime] = None) -> Dict:
    """Reúne todo lo necesario para un reporte: indicadores, accesos, incidentes, agregación y riesgos."""
    return {
        "generado": datetime.now(),
        "modo_bd": repos.bd.modo,
        "indicadores": repos.indicadores(desde, hasta),
        "accesos": repos.accesos.recientes(limite=500, desde=desde, hasta=hasta),
        "incidentes": repos.incidentes.recientes(limite=500, desde=desde, hasta=hasta),
        "incidentes_por_categoria_semana": repos.incidentes.por_categoria_y_semana(),
        "riesgos": servicio_riesgos.listar(),
        "resumen_riesgos": servicio_riesgos.resumen(),
        "evaluaciones_llm": repos.evaluaciones.resumen(),
    }


def reporte_a_lineas(rep: Dict) -> List[str]:
    """Convierte el reporte completo en líneas de texto (para PDF)."""
    ind = rep["indicadores"]
    L = [f"Generado: {rep['generado']:%Y-%m-%d %H:%M}   Base de datos: {rep['modo_bd']}", "",
         "INDICADORES", "-" * 100,
         f"Camiones atendidos: {ind['camiones_atendidos']}   Permitidos: {ind['accesos_permitidos']}   "
         f"Inspecciones: {ind['inspecciones']}   Denegados: {ind['accesos_denegados']}",
         f"Incidentes: {ind['incidentes_total']} (abiertos {ind['incidentes_abiertos']}, criticos {ind['incidentes_criticos']})   "
         f"Riesgos: {ind['riesgos_total']} (criticos {ind['riesgos_criticos']})",
         f"LLM: {ind['llm']['total']} llamadas, latencia media {ind['llm']['latencia_promedio_ms']} ms, "
         f"coincidencia con reglas {ind['llm']['coincidencia_con_reglas']}", "",
         "BITACORA DE ACCESOS", "-" * 100]
    for a in rep["accesos"][:60]:
        p = a["premisas"]
        L.append(f"{a['marca_tiempo']:%Y-%m-%d %H:%M} {str(a.get('camion_id') or '-'):<9}{str(a.get('placa') or '-'):<11}"
                 f"P={int(p['P'])} Q={int(p['Q'])} R={int(p['R'])} S={int(p['S'])} V={int(p['V'])} H={int(p['H'])}  "
                 f"A={int(a['resultado']['A'])} E={int(a['resultado']['E'])}  {a['decision']:<20} {a.get('operador', '')}")
    L += ["", "INCIDENTES", "-" * 100]
    for i in rep["incidentes"][:60]:
        c = i["clasificacion"]
        L.append(f"{i['fecha']:%Y-%m-%d %H:%M} [{c['prioridad']:<7}] {c['categoria']:<22} {i['estado']:<12} "
                 f"{i['correo']['asunto'][:40]}")
    L += ["", "INCIDENTES POR CATEGORIA Y SEMANA (agregacion MongoDB)", "-" * 100]
    for f in rep["incidentes_por_categoria_semana"]:
        L.append(f"{f['anio']}-S{f['semana']:02d}  {f['categoria']:<24} {f['total']}")
    L += ["", "MATRIZ DE RIESGOS ETICOS (inicial -> residual)", "-" * 100]
    for r in rep["riesgos"]:
        L.append(f"[{r['nivel']:<7}->{r['nivel_residual']:<7}] {r['puntaje']:>2}->{r['puntaje_residual']:<2} "
                 f"{r['modulo'][:24]:<24} {r['descripcion'][:50]}")
        if r.get("mitigacion"):
            L.append(f"        Mitigacion: {r['mitigacion'][:90]}")
    rr = rep["resumen_riesgos"]
    L += ["", f"Riesgo promedio inicial {rr['puntaje_promedio']} -> residual {rr['puntaje_residual_promedio']} "
              f"(reduccion {rr['reduccion_pct']}%)"]
    return L
