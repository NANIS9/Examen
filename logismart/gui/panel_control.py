"""Pestaña 1: Panel de control con indicadores y filtro por fecha."""
import tkinter as tk
from tkinter import ttk

from .base import Contexto, Tabla, etiqueta_titulo, parse_fecha, mostrar_error, fmt_fecha, en_hilo, Cargando


class PanelControl(ttk.Frame):
    def __init__(self, master, ctx: Contexto):
        super().__init__(master, padding=12)
        self.ctx = ctx
        etiqueta_titulo(self, "Panel de control")

        filtros = ttk.Frame(self)
        filtros.pack(fill="x")
        ttk.Label(filtros, text="Desde (AAAA-MM-DD):").pack(side="left")
        self.desde = ttk.Entry(filtros, width=12)
        self.desde.pack(side="left", padx=(4, 12))
        ttk.Label(filtros, text="Hasta:").pack(side="left")
        self.hasta = ttk.Entry(filtros, width=12)
        self.hasta.pack(side="left", padx=(4, 12))
        ttk.Button(filtros, text="Aplicar filtro", command=self.refrescar).pack(side="left")
        ttk.Button(filtros, text="Limpiar", command=self._limpiar).pack(side="left", padx=6)
        self.cargando = Cargando(self, "Consultando base de datos...")

        self.tarjetas = ttk.Frame(self)
        self.tarjetas.pack(fill="x", pady=12)
        self._vars = {}
        definiciones = [("camiones_atendidos", "Camiones atendidos", "#1a4d8f"),
                        ("accesos_permitidos", "Accesos estándar", "#2e9e4f"),
                        ("inspecciones", "Inspecciones especiales", "#e3b505"),
                        ("accesos_denegados", "Denegados / retenidos", "#d64545"),
                        ("incidentes_abiertos", "Incidentes abiertos", "#8f3a1a"),
                        ("incidentes_criticos", "Incidentes críticos", "#b00020"),
                        ("riesgos_criticos", "Riesgos críticos", "#6a1b9a"),
                        ("camiones_registrados", "Camiones registrados", "#455a64")]
        for i, (clave, titulo, color) in enumerate(definiciones):
            var = tk.StringVar(value="-")
            self._vars[clave] = var
            tarjeta = tk.Frame(self.tarjetas, bg=color, padx=10, pady=8)
            tarjeta.grid(row=i // 4, column=i % 4, padx=6, pady=6, sticky="nsew")
            tk.Label(tarjeta, textvariable=var, bg=color, fg="white", font=("Segoe UI", 22, "bold")).pack()
            tk.Label(tarjeta, text=titulo, bg=color, fg="white", font=("Segoe UI", 9)).pack()
        for c in range(4):
            self.tarjetas.columnconfigure(c, weight=1)

        self.lbl_llm = ttk.Label(self, text="", foreground="#555")
        self.lbl_llm.pack(anchor="w")

        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill="both", expand=True, pady=(8, 0))
        izq = ttk.Labelframe(cuerpo, text="Últimos accesos", padding=6)
        izq.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.t_accesos = Tabla(izq, [("hora", "Hora", 110), ("camion", "Camión", 80), ("placa", "Placa", 90),
                                     ("decision", "Decisión", 150), ("operador", "Operador", 90)], alto=10)
        self.t_accesos.pack(fill="both", expand=True)
        der = ttk.Labelframe(cuerpo, text="Incidentes por categoría y semana (agregación)", padding=6)
        der.pack(side="left", fill="both", expand=True)
        self.t_agg = Tabla(der, [("semana", "Semana", 80), ("categoria", "Categoría", 180), ("total", "Total", 60)], alto=10)
        self.t_agg.pack(fill="both", expand=True)

        ctx.suscribir(self.refrescar)
        self.refrescar()

    def _limpiar(self):
        self.desde.delete(0, "end")
        self.hasta.delete(0, "end")
        self.refrescar()

    def refrescar(self):
        try:
            desde = parse_fecha(self.desde.get())
            hasta = parse_fecha(self.hasta.get(), fin_del_dia=True)
        except ValueError as exc:
            mostrar_error("Filtro de fecha", str(exc))
            return
        if desde and hasta and desde > hasta:
            mostrar_error("Filtro de fecha", "La fecha 'Desde' no puede ser posterior a 'Hasta'.")
            return
        self.cargando.iniciar()

        def trabajo():
            return (self.ctx.repos.indicadores(desde, hasta),
                    self.ctx.repos.accesos.recientes(limite=30, desde=desde, hasta=hasta),
                    self.ctx.repos.incidentes.por_categoria_y_semana())

        def listo(res):
            self.cargando.detener()
            ind, accesos, agg = res
            for clave, var in self._vars.items():
                var.set(str(ind.get(clave, "-")))
            llm = ind["llm"]
            coinc = f"{llm['coincidencia_con_reglas']:.0%}" if llm["coincidencia_con_reglas"] is not None else "n/d"
            self.lbl_llm.configure(text=f"LLM: {llm['total']} consultas registradas | latencia promedio "
                                        f"{llm['latencia_promedio_ms']} ms | coincidencia LLM-reglas: {coinc}")
            self.t_accesos.llenar([(fmt_fecha(a["marca_tiempo"]), a.get("camion_id") or "-", a.get("placa") or "-",
                                    a["decision"], a.get("operador", "")) for a in accesos], accesos)
            self.t_agg.llenar([(f"{f['anio']}-S{f['semana']:02d}", f["categoria"], f["total"]) for f in agg])

        def fallo(exc):
            self.cargando.detener()
            mostrar_error("Base de datos", f"No se pudieron consultar los indicadores:\n{exc}")

        en_hilo(self, trabajo, listo, fallo)
