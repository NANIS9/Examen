"""Pestaña 7: Reportes. Exportar a PDF / CSV / JSON y ejecutar el experimento de clasificación."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ..clasificador import evaluar_clasificadores, reporte_evaluacion_texto
from ..reportes import exportar_csv, exportar_json, exportar_pdf, generar_reporte_completo, reporte_a_lineas
from .base import (Contexto, Cargando, etiqueta_titulo, texto_scroll, set_texto, parse_fecha, mostrar_error, en_hilo,
                   despachar)


class ReportesGUI(ttk.Frame):
    def __init__(self, master, ctx: Contexto):
        super().__init__(master, padding=12)
        self.ctx = ctx
        etiqueta_titulo(self, "Reportes y exportación")

        f = ttk.Labelframe(self, text="Rango de fechas (opcional)", padding=8)
        f.pack(fill="x")
        ttk.Label(f, text="Desde (AAAA-MM-DD):").pack(side="left")
        self.desde = ttk.Entry(f, width=12); self.desde.pack(side="left", padx=4)
        ttk.Label(f, text="Hasta:").pack(side="left")
        self.hasta = ttk.Entry(f, width=12); self.hasta.pack(side="left", padx=4)

        e = ttk.Labelframe(self, text="Exportar", padding=8)
        e.pack(fill="x", pady=8)
        ttk.Label(e, text="Colección para CSV:").pack(side="left")
        self.cb_col = ttk.Combobox(e, values=("accesos", "incidentes", "riesgos", "camiones", "evaluaciones_llm"), state="readonly", width=16)
        self.cb_col.set("accesos"); self.cb_col.pack(side="left", padx=4)
        ttk.Button(e, text="Exportar CSV", command=self.csv).pack(side="left", padx=4)
        ttk.Button(e, text="Exportar JSON (reporte completo)", command=self.json).pack(side="left", padx=4)
        ttk.Button(e, text="Exportar PDF (reporte completo)", command=self.pdf).pack(side="left", padx=4)

        x = ttk.Labelframe(self, text="Experimento de clasificación (32 correos etiquetados)", padding=8)
        x.pack(fill="x")
        self.incluir_llm = tk.BooleanVar(value=True)
        ttk.Checkbutton(x, text="Incluir LLM e híbrido (requiere Ollama; puede tardar varios minutos)", variable=self.incluir_llm).pack(side="left")
        self.btn_exp = ttk.Button(x, text="Ejecutar experimento", command=self.experimento)
        self.btn_exp.pack(side="left", padx=8)
        ttk.Button(x, text="Guardar resultado", command=self.guardar_experimento).pack(side="left")
        self.cargando = Cargando(self, "Ejecutando...")
        self.txt = texto_scroll(self, alto=20)
        self.txt.configure(state="disabled")
        self.ultimo_experimento = None

    def _rango(self):
        return parse_fecha(self.desde.get()), parse_fecha(self.hasta.get(), fin_del_dia=True)

    def _reporte(self):
        desde, hasta = self._rango()
        return generar_reporte_completo(self.ctx.repos, self.ctx.riesgos, desde, hasta)

    def csv(self):
        try:
            desde, hasta = self._rango()
            col = self.cb_col.get()
            datos = {"accesos": lambda: self.ctx.repos.accesos.recientes(5000, desde, hasta),
                     "incidentes": lambda: self.ctx.repos.incidentes.recientes(5000, desde, hasta),
                     "riesgos": self.ctx.riesgos.listar, "camiones": self.ctx.repos.camiones.listar,
                     "evaluaciones_llm": self.ctx.repos.evaluaciones.listar}[col]()
        except ValueError as exc:
            mostrar_error("Fecha", str(exc)); return
        except Exception as exc:
            mostrar_error("Base de datos", str(exc)); return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"logismart_{col}.csv", filetypes=[("CSV", "*.csv")])
        if ruta:
            exportar_csv(datos, ruta)
            messagebox.showinfo("Exportar", f"{len(datos)} registros exportados a\n{ruta}")

    def json(self):
        try:
            rep = self._reporte()
        except ValueError as exc:
            mostrar_error("Fecha", str(exc)); return
        ruta = filedialog.asksaveasfilename(defaultextension=".json", initialfile="reporte_logismart.json", filetypes=[("JSON", "*.json")])
        if ruta:
            exportar_json(rep, ruta)
            messagebox.showinfo("Exportar", f"Reporte guardado en\n{ruta}")

    def pdf(self):
        try:
            rep = self._reporte()
        except ValueError as exc:
            mostrar_error("Fecha", str(exc)); return
        ruta = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="reporte_logismart.pdf", filetypes=[("PDF", "*.pdf")])
        if ruta:
            exportar_pdf("LogiSmart - Reporte del centro de control", reporte_a_lineas(rep), ruta)
            messagebox.showinfo("Exportar", f"PDF generado en\n{ruta}")
            set_texto(self.txt, "\n".join(reporte_a_lineas(rep)))

    def experimento(self):
        self.btn_exp.configure(state="disabled")
        self.cargando.iniciar("Ejecutando experimento (reglas" + (", LLM e híbrido)..." if self.incluir_llm.get() else ")..."))
        set_texto(self.txt, "")

        def progreso(metodo, i, n):
            despachar(self.cargando.var.set, f"{metodo}: correo {i}/{n}")

        def listo(rep):
            self.cargando.detener()
            self.btn_exp.configure(state="normal")
            self.ultimo_experimento = rep
            set_texto(self.txt, reporte_evaluacion_texto(rep))

        def fallo(exc):
            self.cargando.detener()
            self.btn_exp.configure(state="normal")
            mostrar_error("Experimento", str(exc))

        en_hilo(self, lambda: evaluar_clasificadores(self.ctx.llm, self.incluir_llm.get(), progreso=progreso), listo, fallo)

    def guardar_experimento(self):
        if not self.ultimo_experimento:
            mostrar_error("Experimento", "Primero ejecuta el experimento.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".json", initialfile="experimento_clasificacion.json", filetypes=[("JSON", "*.json")])
        if ruta:
            exportar_json(self.ultimo_experimento, ruta)
            exportar_pdf("LogiSmart - Experimento de clasificación", reporte_evaluacion_texto(self.ultimo_experimento).split("\n"),
                         ruta.rsplit(".", 1)[0] + ".pdf")
            messagebox.showinfo("Experimento", f"Guardado en {ruta} (y .pdf)")
