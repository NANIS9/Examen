"""Ventana principal: crea los servicios, las pestañas y la barra de estado (MongoDB / Ollama)."""
import tkinter as tk
from tkinter import ttk

from ..asistente import Asistente
from ..clasificador import ClasificadorHibrido, ClienteOllama
from ..config import config
from ..db import BaseDatos, Repositorios
from ..riesgos import ServicioRiesgos
from .asistente import AsistenteGUI
from .bandeja import BandejaIncidentes
from .base import Contexto, en_hilo, bombear
from .camiones import CamionesGUI
from .configuracion import ConfiguracionGUI
from .control_acceso import ControlAcceso
from .panel_control import PanelControl
from .reportes import ReportesGUI
from .riesgos import RiesgosGUI
from .simulador import Simulador


class AplicacionLogiSmart(tk.Tk):
    def __init__(self, forzar_memoria: bool = False):
        super().__init__()
        self.title("LogiSmart - Centro de control inteligente")
        self.geometry("1280x800")
        self.minsize(1024, 680)
        try:
            ttk.Style(self).theme_use("vista")
        except tk.TclError:
            pass

        # --- Servicios (capas inferiores) ---------------------------------------
        repos = Repositorios(BaseDatos(forzar_memoria=forzar_memoria))
        llm = ClienteOllama()
        clasificador = ClasificadorHibrido(llm=llm, repos=repos)
        asistente = Asistente(repos, llm)
        riesgos = ServicioRiesgos(repos)
        self.ctx = Contexto(repos, llm, clasificador, asistente, riesgos, config)

        # --- Pestañas --------------------------------------------------------------
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        nb.add(PanelControl(nb, self.ctx), text=" Panel de control ")
        nb.add(ControlAcceso(nb, self.ctx), text=" Control de acceso ")
        nb.add(Simulador(nb, self.ctx), text=" Simulador lógico ")
        nb.add(BandejaIncidentes(nb, self.ctx), text=" Bandeja de incidentes ")
        nb.add(AsistenteGUI(nb, self.ctx), text=" Asistente LLM ")
        nb.add(RiesgosGUI(nb, self.ctx), text=" Riesgos éticos ")
        nb.add(CamionesGUI(nb, self.ctx), text=" Camiones ")
        nb.add(ReportesGUI(nb, self.ctx), text=" Reportes ")
        nb.add(ConfiguracionGUI(nb, self.ctx, al_cambiar_conexion=self._actualizar_estado), text=" Configuración ")

        # --- Barra de estado -----------------------------------------------------------
        barra = tk.Frame(self, bg="#263238")
        barra.pack(fill="x", side="bottom")
        self.lbl_mongo = tk.Label(barra, text="", bg="#263238", fg="white", anchor="w", padx=8)
        self.lbl_mongo.pack(side="left")
        self.lbl_ollama = tk.Label(barra, text="Ollama: verificando...", bg="#263238", fg="#ffd54f", anchor="e", padx=8)
        self.lbl_ollama.pack(side="right")
        self._actualizar_estado()
        bombear(self)           # arranca el procesamiento de resultados de hilos secundarios
        en_hilo(self, llm.disponible, self._estado_ollama, lambda e: self._estado_ollama((False, str(e))))

    def _actualizar_estado(self):
        est = self.ctx.repos.bd.estado()
        if est["modo"] == "mongo":
            self.lbl_mongo.configure(text=f"MongoDB: conectado ({est['uri']} / {est['base']})", fg="#a5d6a7")
        else:
            self.lbl_mongo.configure(text="MongoDB: SIN CONEXIÓN - modo memoria (ver pestaña Configuración)", fg="#ef9a9a")
        ok, msg = self.ctx.ollama_estado
        self.lbl_ollama.configure(text=f"Ollama: {'OK' if ok else 'no disponible'} - {msg[:80]}", fg="#a5d6a7" if ok else "#ef9a9a")

    def _estado_ollama(self, r):
        self.ctx.ollama_estado = r
        self._actualizar_estado()


def iniciar(forzar_memoria: bool = False) -> None:
    app = AplicacionLogiSmart(forzar_memoria=forzar_memoria)
    app.mainloop()
