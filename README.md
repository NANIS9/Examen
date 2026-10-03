# LogiSmart — Centro de control inteligente (MongoDB + Ollama + tkinter)

Práctica de Fundamentos de IA. Dos entregables:

| Archivo | Descripción |
|---------|-------------|
| `p02primertutor_llm.py` | Práctica 1: tutor con LLM ("Chef Sazón") con interfaz gráfica y resumen del historial. |
| `logiuncodigo.py` + `logismart/` | Práctica 2: aplicación modular con MongoDB, motor de reglas, clasificador híbrido (reglas + LLM), asistente RAG, matriz de riesgos éticos, reportes y GUI. |

## Inicio rápido

```powershell
python -m pip install -r requirements.txt
ollama pull llama3.2            # LLM local (ver docs/INSTALACION.md)
python logiuncodigo.py --demo   # carga datos de demostración en MongoDB
python logiuncodigo.py          # abre la interfaz gráfica
python logiuncodigo.py --tests  # 31 pruebas unitarias
```

Sin MongoDB la app funciona en modo memoria (`--memoria`); sin Ollama usa el clasificador por reglas.

## Documentación

* `docs/INSTALACION.md` — pasos detallados para Ollama, MongoDB (Atlas/Compass), Git y la exposición.
* `docs/INFORME_TECNICO.md` — arquitectura, esquema de colecciones, prompts, experimento y análisis ético.
* `docs/resultados_experimento.json` — salida del experimento de clasificación.
* `legacy/logiuncodigo_monolitico.py` — script original antes de la refactorización.

## Estructura

```
logismart/
  config.py          configuración (config.json / variables de entorno)
  db/                conexión MongoDB + respaldo en memoria, repositorios, agregación
  reglas/            A, E, B, X · tablas de verdad · explicación · análisis de reglas
  clasificador/      reglas, LLM (pydantic + reintentos), híbrido, evaluación (32 correos)
  asistente/         chat RAG sobre MongoDB con citas
  riesgos/           matriz de riesgos con riesgo residual
  reportes/          CSV / JSON / PDF
  datos/             correos etiquetados y datos demo
  gui/               9 pestañas tkinter
tests/               pruebas unitarias y de humo de la GUI
```
