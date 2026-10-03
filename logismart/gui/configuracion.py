"""Pestaña 8: Configuración. Modelo de Ollama, umbrales, modo simulación de correo, MongoDB y datos demo."""
import tkinter as tk
from tkinter import ttk, messagebox

from ..datos import cargar_demo
from .base import Contexto, Cargando, etiqueta_titulo, mostrar_error, en_hilo


class ConfiguracionGUI(ttk.Frame):
    def __init__(self, master, ctx: Contexto, al_cambiar_conexion=None):
        super().__init__(master, padding=12)
        self.ctx = ctx
        self.al_cambiar_conexion = al_cambiar_conexion
        cfg = ctx.config
        etiqueta_titulo(self, "Configuración")

        # --- Ollama ----------------------------------------------------------------
        o = ttk.Labelframe(self, text="LLM local (Ollama)", padding=8)
        o.pack(fill="x", pady=4)
        ttk.Label(o, text="Servidor:").grid(row=0, column=0, sticky="w")
        self.e_host = ttk.Entry(o, width=32); self.e_host.insert(0, cfg.ollama_host); self.e_host.grid(row=0, column=1, sticky="w")
        ttk.Label(o, text="Modelo:").grid(row=1, column=0, sticky="w")
        self.cb_modelo = ttk.Combobox(o, width=30, values=[cfg.modelo_llm]); self.cb_modelo.set(cfg.modelo_llm)
        self.cb_modelo.grid(row=1, column=1, sticky="w")
        ttk.Button(o, text="Detectar modelos", command=self.detectar).grid(row=1, column=2, padx=6)
        ttk.Label(o, text="Reintentos JSON:").grid(row=2, column=0, sticky="w")
        self.s_reint = ttk.Spinbox(o, from_=0, to=5, width=5); self.s_reint.set(cfg.llm_reintentos); self.s_reint.grid(row=2, column=1, sticky="w")
        ttk.Label(o, text="Temperatura:").grid(row=3, column=0, sticky="w")
        self.e_temp = ttk.Entry(o, width=6); self.e_temp.insert(0, str(cfg.llm_temperatura)); self.e_temp.grid(row=3, column=1, sticky="w")
        self.lbl_ollama = ttk.Label(o, text="", foreground="#555", wraplength=600)
        self.lbl_ollama.grid(row=4, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Button(o, text="Probar conexión", command=self.probar_ollama).grid(row=0, column=2, padx=6)

        # --- Umbrales ----------------------------------------------------------------------
        u = ttk.Labelframe(self, text="Umbrales del motor de reglas", padding=8)
        u.pack(fill="x", pady=4)
        ttk.Label(u, text="Peso máximo (kg):").grid(row=0, column=0, sticky="w")
        self.e_peso = ttk.Entry(u, width=10); self.e_peso.insert(0, str(cfg.peso_maximo_kg)); self.e_peso.grid(row=0, column=1, sticky="w")
        ttk.Label(u, text="Horario materiales peligrosos: de").grid(row=1, column=0, sticky="w")
        self.s_h1 = ttk.Spinbox(u, from_=0, to=23, width=4); self.s_h1.set(cfg.hora_inicio_peligrosos); self.s_h1.grid(row=1, column=1, sticky="w")
        ttk.Label(u, text="a").grid(row=1, column=2)
        self.s_h2 = ttk.Spinbox(u, from_=1, to=24, width=4); self.s_h2.set(cfg.hora_fin_peligrosos); self.s_h2.grid(row=1, column=3, sticky="w")
        ttk.Label(u, text="hrs").grid(row=1, column=4)

        # --- Correo / operador -----------------------------------------------------------------
        c = ttk.Labelframe(self, text="Correo y operador", padding=8)
        c.pack(fill="x", pady=4)
        self.v_sim = tk.BooleanVar(value=cfg.modo_simulacion_correo)
        ttk.Checkbutton(c, text="Modo simulación de correo (no envía correos reales)", variable=self.v_sim).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(c, text="Correo de soporte:").grid(row=1, column=0, sticky="w")
        self.e_soporte = ttk.Entry(c, width=32); self.e_soporte.insert(0, cfg.correo_soporte); self.e_soporte.grid(row=1, column=1, sticky="w")
        ttk.Label(c, text="Operador actual:").grid(row=2, column=0, sticky="w")
        self.e_oper = ttk.Entry(c, width=20); self.e_oper.insert(0, cfg.operador); self.e_oper.grid(row=2, column=1, sticky="w")

        # --- MongoDB -------------------------------------------------------------------------
        m = ttk.Labelframe(self, text="MongoDB", padding=8)
        m.pack(fill="x", pady=4)
        ttk.Label(m, text="URI (local o Atlas):").grid(row=0, column=0, sticky="w")
        self.e_uri = ttk.Entry(m, width=60); self.e_uri.insert(0, cfg.mongo_uri); self.e_uri.grid(row=0, column=1, sticky="w")
        ttk.Label(m, text="Base de datos:").grid(row=1, column=0, sticky="w")
        self.e_db = ttk.Entry(m, width=20); self.e_db.insert(0, cfg.mongo_db); self.e_db.grid(row=1, column=1, sticky="w")
        ttk.Button(m, text="Reconectar", command=self.reconectar).grid(row=0, column=2, padx=6)
        self.lbl_mongo = ttk.Label(m, text="", foreground="#555", wraplength=600)
        self.lbl_mongo.grid(row=2, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Button(m, text="Cargar datos de demostración (borra lo existente)", command=self.demo).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)

        fila = ttk.Frame(self)
        fila.pack(fill="x", pady=10)
        ttk.Button(fila, text="Guardar configuración", command=self.guardar).pack(side="left")
        self.cargando = Cargando(self, "Trabajando...")
        self._mostrar_estado_mongo()

    # ------------------------------------------------------------------
    def _mostrar_estado_mongo(self):
        est = self.ctx.repos.bd.estado()
        if est["modo"] == "mongo":
            self.lbl_mongo.configure(text=f"Conectado a MongoDB: {est['uri']} / {est['base']}", foreground="#2e7d32")
        else:
            self.lbl_mongo.configure(text=f"SIN CONEXIÓN a MongoDB -> trabajando en memoria (los datos se pierden al cerrar). "
                                          f"{est['error'] or ''}", foreground="#c62828")

    def guardar(self):
        cfg = self.ctx.config
        try:
            peso = float(self.e_peso.get())
            if peso <= 0:
                raise ValueError
        except ValueError:
            mostrar_error("Validación", "El peso máximo debe ser un número positivo (kg).")
            return
        try:
            h1, h2 = int(self.s_h1.get()), int(self.s_h2.get())
            if not 0 <= h1 < h2 <= 24:
                raise ValueError
        except ValueError:
            mostrar_error("Validación", "El horario debe cumplir 0 <= inicio < fin <= 24.")
            return
        try:
            temp = float(self.e_temp.get())
            if not 0 <= temp <= 2:
                raise ValueError
        except ValueError:
            mostrar_error("Validación", "La temperatura debe estar entre 0 y 2.")
            return
        if not self.e_oper.get().strip():
            mostrar_error("Validación", "El operador no puede estar vacío.")
            return
        cfg.ollama_host, cfg.modelo_llm = self.e_host.get().strip(), self.cb_modelo.get().strip()
        cfg.llm_reintentos, cfg.llm_temperatura = int(self.s_reint.get()), temp
        cfg.peso_maximo_kg, cfg.hora_inicio_peligrosos, cfg.hora_fin_peligrosos = peso, h1, h2
        cfg.modo_simulacion_correo, cfg.correo_soporte = self.v_sim.get(), self.e_soporte.get().strip()
        cfg.operador = self.e_oper.get().strip()
        cfg.mongo_uri, cfg.mongo_db = self.e_uri.get().strip(), self.e_db.get().strip()
        self.ctx.llm.modelo, self.ctx.llm.host, self.ctx.llm._cliente = cfg.modelo_llm, cfg.ollama_host, None
        cfg.guardar()
        messagebox.showinfo("Configuración", "Configuración guardada en config.json.")

    def probar_ollama(self):
        self.ctx.llm.modelo, self.ctx.llm.host, self.ctx.llm._cliente = self.cb_modelo.get().strip(), self.e_host.get().strip(), None
        self.cargando.iniciar("Consultando Ollama...")

        def listo(r):
            self.cargando.detener()
            ok, msg = r
            self.ctx.ollama_estado = r
            self.lbl_ollama.configure(text=msg, foreground="#2e7d32" if ok else "#c62828")
            if self.al_cambiar_conexion:
                self.al_cambiar_conexion()

        en_hilo(self, self.ctx.llm.disponible, listo, lambda e: (self.cargando.detener(), mostrar_error("Ollama", str(e))))

    def detectar(self):
        self.ctx.llm.host, self.ctx.llm._cliente = self.e_host.get().strip(), None
        self.cargando.iniciar("Buscando modelos...")

        def listo(modelos):
            self.cargando.detener()
            if modelos:
                self.cb_modelo.configure(values=modelos)
                if self.cb_modelo.get() not in modelos:
                    self.cb_modelo.set(modelos[0])
                self.lbl_ollama.configure(text=f"Modelos disponibles: {', '.join(modelos)}", foreground="#2e7d32")
            else:
                self.lbl_ollama.configure(text="Ollama responde pero no hay modelos. Ejecuta: ollama pull llama3.2", foreground="#c62828")

        def fallo(exc):
            self.cargando.detener()
            self.lbl_ollama.configure(text=str(exc), foreground="#c62828")

        en_hilo(self, self.ctx.llm.modelos, listo, fallo)

    def reconectar(self):
        bd = self.ctx.repos.bd
        bd.uri, bd.nombre = self.e_uri.get().strip(), self.e_db.get().strip()
        self.cargando.iniciar("Conectando a MongoDB...")

        def listo(ok):
            self.cargando.detener()
            self._mostrar_estado_mongo()
            if self.al_cambiar_conexion:
                self.al_cambiar_conexion()
            self.ctx.notificar()
            if not ok:
                mostrar_error("MongoDB", f"No se pudo conectar.\n{bd.error}\n\nRevisa que MongoDB esté en ejecución o que la URI de Atlas "
                                         "sea correcta (ver docs/INSTALACION.md). Mientras tanto se trabaja en memoria.")

        en_hilo(self, bd.conectar, listo, lambda e: (self.cargando.detener(), mostrar_error("MongoDB", str(e))))

    def demo(self):
        if not messagebox.askyesno("Datos demo", "Esto BORRA todas las colecciones y carga datos de demostración.\n¿Continuar?"):
            return
        self.cargando.iniciar("Cargando datos de demostración...")

        def listo(res):
            self.cargando.detener()
            self.ctx.notificar()
            messagebox.showinfo("Datos demo", f"Cargado en modo '{res['modo_bd']}': {res['camiones']} camiones, {res['accesos']} accesos, "
                                              f"{res['incidentes']} incidentes, {res['riesgos']} riesgos.")

        en_hilo(self, lambda: cargar_demo(self.ctx.repos, self.ctx.riesgos), listo,
                lambda e: (self.cargando.detener(), mostrar_error("Datos demo", str(e))))
