#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
 LogiSmart  -  Centro de control inteligente de acceso y seguridad logística
==============================================================================
Punto de entrada de la aplicación modular (paquete `logismart/`):

  python logiuncodigo.py              -> abre la interfaz gráfica (conecta a MongoDB; si falla, modo memoria)
  python logiuncodigo.py --demo       -> carga datos de demostración en MongoDB y sale
  python logiuncodigo.py --memoria    -> abre la GUI sin intentar conectar a MongoDB (demo en memoria)
  python logiuncodigo.py --tests      -> ejecuta las pruebas unitarias (carpeta tests/)
  python logiuncodigo.py --experimento -> corre el experimento de clasificación en consola
  python logiuncodigo.py --tablas     -> imprime las tablas de verdad y el análisis de reglas

Arquitectura por capas:
  logismart/config.py        configuración (config.json / variables de entorno)
  logismart/db/              MongoDB: conexión, repositorios, agregación, respaldo en memoria
  logismart/reglas/          motor de lógica proposicional (A, E, B, X) + tablas de verdad
  logismart/clasificador/    reglas, LLM (Ollama + pydantic), híbrido, evaluación
  logismart/asistente/       chat RAG sobre MongoDB
  logismart/riesgos/         matriz de riesgos éticos con riesgo residual
  logismart/reportes/        exportación CSV / JSON / PDF
  logismart/gui/             interfaz gráfica tkinter
  legacy/                    script monolítico original (referencia)
==============================================================================
"""
import sys


def main(argv):
    if "--tests" in argv:
        import unittest
        suite = unittest.defaultTestLoader.discover("tests")
        resultado = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if resultado.wasSuccessful() else 1

    if "--tablas" in argv:
        from logismart.reglas import REGLAS, tabla_texto, analizar_reglas
        for letra in REGLAS:
            print(tabla_texto(letra), "\n")
        print("Análisis de reglas:")
        for h in analizar_reglas():
            print(f"  [{h['tipo']}] {h['detalle']}")
        return 0

    if "--experimento" in argv:
        from logismart.clasificador import evaluar_clasificadores, reporte_evaluacion_texto
        from logismart.reportes import exportar_json
        rep = evaluar_clasificadores(incluir_llm="--sin-llm" not in argv,
                                     progreso=lambda m, i, n: print(f"\r{m}: {i}/{n}", end="", flush=True))
        print("\n" + reporte_evaluacion_texto(rep))
        exportar_json(rep, "docs/resultados_experimento.json")
        print("\nGuardado en docs/resultados_experimento.json")
        return 0

    if "--demo" in argv:
        from logismart.db import BaseDatos, Repositorios
        from logismart.riesgos import ServicioRiesgos
        from logismart.datos import cargar_demo
        repos = Repositorios(BaseDatos())
        print("Base de datos:", repos.bd.estado())
        if repos.bd.modo != "mongo":
            print("ADVERTENCIA: sin conexión a MongoDB; los datos demo sólo vivirían en memoria. Revisa docs/INSTALACION.md")
            return 1
        print("Datos cargados:", cargar_demo(repos, ServicioRiesgos(repos)))
        return 0

    from logismart.gui import iniciar
    iniciar(forzar_memoria="--memoria" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
