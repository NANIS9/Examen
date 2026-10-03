"""Pestaña 5: Asistente (chat LLM con RAG). Conversación con historial y fuentes consultadas."""
import tkinter as tk
from tkinter import ttk

from .base import Contexto, Cargando, etiqueta_titulo, mostrar_error, en_hilo

SUGERENCIAS = ["¿Por qué CAM-102 fue enviado a inspección?", "¿Por qué se denegó el acceso a CAM-077?",
               "¿Qué incidentes abiertos hay?", "¿Cuáles son los riesgos éticos más altos?",
               "Dame un resumen de los indicadores de hoy", "¿Qué reglas lógicas usa el sistema?"]


class AsistenteGUI(ttk.Frame):
    def __init__(self, master, ctx: Contexto):
        super().__init__(master, padding=12)
        self.ctx = ctx
        etiqueta_titulo(self, "Asistente explicativo (LLM + MongoDB)")
        ttk.Label(self, text="El asistente responde únicamente con datos recuperados de MongoDB y cita el registro de origen "
                             "[coleccion:id]. Si no hay datos responde 'no tengo información'.",
                  wraplength=900, foreground="#555").pack(anchor="w")

        cuerpo = ttk.Panedwindow(self, orient="horizontal")
        cuerpo.pack(fill="both", expand=True, pady=8)
        izq = ttk.Frame(cuerpo)
        cuerpo.add(izq, weight=3)
        self.chat = tk.Text(izq, wrap="word", state="disabled", font=("Segoe UI", 10), padx=8, pady=8)
        sb = ttk.Scrollbar(izq, command=self.chat.yview)
        self.chat.configure(yscrollcommand=sb.set)
        self.chat.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.chat.tag_config("op", foreground="#1a4d8f", font=("Segoe UI", 10, "bold"))
        self.chat.tag_config("ia", foreground="#2e7d32", font=("Segoe UI", 10, "bold"))
        self.chat.tag_config("fuente", foreground="#777", font=("Segoe UI", 9, "italic"))

        der = ttk.Labelframe(cuerpo, text="Fuentes consultadas", padding=6)
        cuerpo.add(der, weight=1)
        self.lst_fuentes = tk.Listbox(der, height=12, font=("Consolas", 9))
        self.lst_fuentes.pack(fill="both", expand=True)
        ttk.Label(der, text="Preguntas sugeridas:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 2))
        for s in SUGERENCIAS:
            ttk.Button(der, text=s, command=lambda q=s: self._poner(q)).pack(fill="x", pady=1)

        self.cargando = Cargando(self, "El LLM está redactando la respuesta...")
        abajo = ttk.Frame(self)
        abajo.pack(fill="x")
        self.entrada = ttk.Entry(abajo, font=("Segoe UI", 10))
        self.entrada.pack(side="left", fill="x", expand=True)
        self.entrada.bind("<Return>", lambda _e: self.preguntar())
        self.btn = ttk.Button(abajo, text="Preguntar", command=self.preguntar)
        self.btn.pack(side="left", padx=6)
        ttk.Button(abajo, text="Limpiar", command=self.limpiar).pack(side="left")

    def _poner(self, q):
        self.entrada.delete(0, "end")
        self.entrada.insert(0, q)
        self.preguntar()

    def _escribir(self, quien, texto, tag):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{quien}:\n", tag)
        self.chat.insert("end", texto.strip() + "\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def preguntar(self):
        q = self.entrada.get().strip()
        if not q:
            mostrar_error("Asistente", "Escribe una pregunta.")
            return
        if len(q) > 500:
            mostrar_error("Asistente", "La pregunta es demasiado larga (máximo 500 caracteres).")
            return
        self.entrada.delete(0, "end")
        self._escribir("Operador", q, "op")
        self.btn.configure(state="disabled")
        self.cargando.iniciar()

        def listo(r):
            self.cargando.detener()
            self.btn.configure(state="normal")
            extra = f"  [{r['modo']} | {r['latencia_ms']} ms]" if r["modo"] == "llm" else f"  [{r['modo']}]"
            self._escribir("Asistente", r["texto"], "ia")
            self.chat.configure(state="normal")
            self.chat.insert("end", (f"Fuentes: {', '.join(r['fuentes'])}" if r["fuentes"] else "Fuentes: ninguna") + extra + "\n\n", "fuente")
            self.chat.configure(state="disabled")
            self.lst_fuentes.delete(0, "end")
            for f in r["fuentes"]:
                self.lst_fuentes.insert("end", f)

        def fallo(exc):
            self.cargando.detener()
            self.btn.configure(state="normal")
            mostrar_error("Asistente", f"No se pudo responder:\n{exc}")

        en_hilo(self, lambda: self.ctx.asistente.responder(q), listo, fallo)

    def limpiar(self):
        self.ctx.asistente.historial.clear()
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.lst_fuentes.delete(0, "end")
