"""
LogiSmart - Centro de control inteligente de acceso y seguridad logística.

Arquitectura por capas:
    config        -> parámetros de la aplicación (Mongo, Ollama, umbrales)
    db            -> persistencia en MongoDB (con respaldo en memoria)
    reglas        -> motor de lógica proposicional (A, E y reglas nuevas)
    clasificador  -> clasificador híbrido (reglas + LLM) y evaluación
    asistente     -> chat RAG explicativo sobre los datos de MongoDB
    riesgos       -> matriz de riesgos éticos con riesgo residual
    reportes      -> exportación CSV / JSON / PDF
    gui           -> interfaz gráfica tkinter
"""
__version__ = "2.0.0"
