"""Pestaña 6: Matriz de riesgos éticos. Gráfica (mapa de calor 5x5 + barras inicial vs residual), alta/edición/baja."""
import tkinter as tk
from tkinter import ttk, messagebox

from ..riesgos import CATEGORIAS_RIESGO, NIVELES
from .base import Contexto, Tabla, etiqueta_titulo, mostrar_error, texto_scroll, set_texto, fmt_fecha

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAY_MPL = True
except ImportError:          # Sin matplotlib se dibuja con Canvas de tkinter
    HAY_MPL = False

COLOR_NIVEL = {"bajo": "#8bc34a", "medio": "#ffeb3b", "alto": "#ff9800", "crítico": "#f44336"}


class RiesgosGUI(ttk.Frame):
    def __init__(self, master, ctx: Contexto):
        super().__init__(master, padding=12)
        self.ctx = ctx
        etiqueta_titulo(self, "Matriz de riesgos éticos")
        cuerpo = ttk.Panedwindow(self, orient="horizontal")
        cuerpo.pack(fill="both", expand=True)

        # --- Formulario -------------------------------------------------------------
        form = ttk.Labelframe(cuerpo, text="Alta / edición de riesgo", padding=8)
        cuerpo.add(form, weight=1)
        self.e_modulo = ttk.Entry(form, width=36)
        self.e_desc = tk.Text(form, width=36, height=3, wrap="word")
        self.cb_cat = ttk.Combobox(form, values=CATEGORIAS_RIESGO, state="readonly", width=20)
        self.e_mit = tk.Text(form, width=36, height=3, wrap="word")
        self.escalas = {}
        filas = [("Módulo:", self.e_modulo), ("Descripción:", self.e_desc), ("Categoría:", self.cb_cat)]
        r = 0
        for texto, w in filas:
            ttk.Label(form, text=texto).grid(row=r, column=0, sticky="nw", pady=2)
            w.grid(row=r, column=1, columnspan=3, sticky="ew", pady=2)
            r += 1
        for texto, clave in (("Probabilidad (1-5):", "probabilidad"), ("Impacto (1-5):", "impacto"),
                             ("Prob. residual:", "probabilidad_residual"), ("Impacto residual:", "impacto_residual")):
            ttk.Label(form, text=texto).grid(row=r, column=0, sticky="w", pady=2)
            var = tk.IntVar(value=3)
            self.escalas[clave] = var
            ttk.Spinbox(form, from_=1, to=5, textvariable=var, width=5).grid(row=r, column=1, sticky="w")
            r += 1
        ttk.Label(form, text="Mitigación:").grid(row=r, column=0, sticky="nw", pady=2)
        self.e_mit.grid(row=r, column=1, columnspan=3, sticky="ew")
        r += 1
        self.lbl_puntaje = ttk.Label(form, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_puntaje.grid(row=r, column=0, columnspan=4, sticky="w", pady=4)
        for v in self.escalas.values():
            v.trace_add("write", lambda *_: self._previsualizar())
        r += 1
        b = ttk.Frame(form)
        b.grid(row=r, column=0, columnspan=4, sticky="w", pady=6)
        ttk.Button(b, text="Crear", command=self.crear).pack(side="left")
        ttk.Button(b, text="Guardar cambios", command=self.actualizar).pack(side="left", padx=4)
        ttk.Button(b, text="Eliminar", command=self.eliminar).pack(side="left")
        ttk.Button(b, text="Limpiar", command=self.limpiar).pack(side="left", padx=4)
        form.columnconfigure(1, weight=1)
        self._id = None

        ttk.Label(form, text="Histórico del riesgo seleccionado:", font=("Segoe UI", 9, "bold")).grid(row=r + 1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        marco_h = ttk.Frame(form)
        marco_h.grid(row=r + 2, column=0, columnspan=4, sticky="nsew")
        self.t_hist = texto_scroll(marco_h, alto=6)
        self.t_hist.configure(state="disabled")

        # --- Derecha: tabla + gráficas ---------------------------------------------------
        der = ttk.Frame(cuerpo, padding=(8, 0, 0, 0))
        cuerpo.add(der, weight=3)
        self.tabla = Tabla(der, [("nivel", "Nivel", 60), ("pts", "Pts", 40), ("res", "Residual", 60), ("modulo", "Módulo", 150),
                                 ("cat", "Categoría", 100), ("desc", "Descripción", 320)], alto=8)
        self.tabla.pack(fill="x")
        for n, c in COLOR_NIVEL.items():
            self.tabla.tree.tag_configure(n, background=c)
        self.tabla.al_seleccionar(self.cargar)
        self.lbl_resumen = ttk.Label(der, text="", foreground="#555")
        self.lbl_resumen.pack(anchor="w", pady=4)

        self.marco_graf = ttk.Frame(der)
        self.marco_graf.pack(fill="both", expand=True)
        self._canvas = None
        ctx.suscribir(self.refrescar)
        self.refrescar()

    # ------------------------------------------------------------------
    def _previsualizar(self):
        try:
            p, i = self.escalas["probabilidad"].get(), self.escalas["impacto"].get()
            pr, ir = self.escalas["probabilidad_residual"].get(), self.escalas["impacto_residual"].get()
        except tk.TclError:
            return
        from ..riesgos import calcular_nivel
        self.lbl_puntaje.configure(text=f"Puntaje inicial {p * i} ({calcular_nivel(p * i)})  ->  residual {pr * ir} ({calcular_nivel(pr * ir)})")

    def _leer(self):
        return {"modulo": self.e_modulo.get(), "descripcion": self.e_desc.get("1.0", "end").strip(),
                "categoria": self.cb_cat.get(), "mitigacion": self.e_mit.get("1.0", "end").strip(),
                **{k: v.get() for k, v in self.escalas.items()}}

    def crear(self):
        try:
            self.ctx.riesgos.crear(self._leer(), self.ctx.operador)
        except (ValueError, tk.TclError) as exc:
            mostrar_error("Validación", str(exc))
            return
        except Exception as exc:
            mostrar_error("Base de datos", str(exc))
            return
        self.limpiar()
        self.ctx.notificar()

    def actualizar(self):
        if not self._id:
            mostrar_error("Riesgos", "Selecciona un riesgo de la tabla para editarlo.")
            return
        try:
            self.ctx.riesgos.actualizar(self._id, self._leer(), self.ctx.operador)
        except (ValueError, tk.TclError) as exc:
            mostrar_error("Validación", str(exc))
            return
        self.ctx.notificar()

    def eliminar(self):
        if not self._id:
            mostrar_error("Riesgos", "Selecciona un riesgo de la tabla.")
            return
        if messagebox.askyesno("Eliminar", "¿Eliminar el riesgo seleccionado?"):
            self.ctx.riesgos.eliminar(self._id)
            self.limpiar()
            self.ctx.notificar()

    def limpiar(self):
        self._id = None
        self.e_modulo.delete(0, "end")
        self.e_desc.delete("1.0", "end")
        self.e_mit.delete("1.0", "end")
        self.cb_cat.set("")
        for v in self.escalas.values():
            v.set(3)
        set_texto(self.t_hist, "")

    def cargar(self, d):
        self._id = d["_id"]
        self.e_modulo.delete(0, "end"); self.e_modulo.insert(0, d["modulo"])
        self.e_desc.delete("1.0", "end"); self.e_desc.insert("1.0", d["descripcion"])
        self.e_mit.delete("1.0", "end"); self.e_mit.insert("1.0", d.get("mitigacion", ""))
        self.cb_cat.set(d["categoria"])
        for k, v in self.escalas.items():
            v.set(d.get(k, 3))
        set_texto(self.t_hist, "\n".join(f"{fmt_fecha(h['fecha'])} {h['accion']}: {h['puntaje']} -> {h['puntaje_residual']} ({h.get('operador')})"
                                         for h in d.get("historico", [])))

    # ------------------------------------------------------------------
    def refrescar(self):
        try:
            riesgos = self.ctx.riesgos.listar()
            res = self.ctx.riesgos.resumen()
            m_ini, m_res = self.ctx.riesgos.matriz_5x5(False), self.ctx.riesgos.matriz_5x5(True)
        except Exception as exc:
            mostrar_error("Base de datos", f"No se pudo leer riesgos_eticos:\n{exc}")
            return
        self.tabla.llenar([(r["nivel"], r["puntaje"], f"{r['puntaje_residual']} ({r['nivel_residual']})", r["modulo"],
                            r["categoria"], r["descripcion"][:80]) for r in riesgos], riesgos, tags=[r["nivel"] for r in riesgos])
        self.lbl_resumen.configure(text=f"{res['total']} riesgos | por nivel: {res['por_nivel']} | promedio inicial "
                                        f"{res['puntaje_promedio']} -> residual {res['puntaje_residual_promedio']} "
                                        f"(reducción {res['reduccion_pct']}%)")
        self._dibujar(m_ini, m_res, riesgos)

    def _dibujar(self, m_ini, m_res, riesgos):
        for w in self.marco_graf.winfo_children():
            w.destroy()
        if HAY_MPL:
            fig = Figure(figsize=(9, 3.4), dpi=90)
            for idx, (m, titulo) in enumerate(((m_ini, "Matriz inicial (P x I)"), (m_res, "Matriz residual"))):
                ax = fig.add_subplot(1, 3, idx + 1)
                fondo = [[p * i for p in range(1, 6)] for i in range(1, 6)]
                ax.imshow(fondo, cmap="RdYlGn_r", vmin=1, vmax=25, origin="lower")
                for i in range(5):
                    for p in range(5):
                        if m[i][p]:
                            ax.text(p, i, str(m[i][p]), ha="center", va="center", fontsize=11, fontweight="bold")
                ax.set_xticks(range(5)); ax.set_xticklabels(range(1, 6)); ax.set_yticks(range(5)); ax.set_yticklabels(range(1, 6))
                ax.set_xlabel("Probabilidad"); ax.set_ylabel("Impacto"); ax.set_title(titulo, fontsize=9)
            ax = fig.add_subplot(1, 3, 3)
            top = riesgos[:8]
            y = range(len(top))
            ax.barh([i + 0.2 for i in y], [r["puntaje"] for r in top], height=0.4, label="Inicial", color="#f44336")
            ax.barh([i - 0.2 for i in y], [r["puntaje_residual"] for r in top], height=0.4, label="Residual", color="#8bc34a")
            ax.set_yticks(list(y)); ax.set_yticklabels([r["descripcion"][:22] + "…" for r in top], fontsize=6)
            ax.invert_yaxis(); ax.set_xlim(0, 25); ax.set_title("Inicial vs residual", fontsize=9); ax.legend(fontsize=7)
            fig.tight_layout()
            self._canvas = FigureCanvasTkAgg(fig, master=self.marco_graf)
            self._canvas.draw()
            self._canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            self._dibujar_canvas(m_ini)

    def _dibujar_canvas(self, m):
        c = tk.Canvas(self.marco_graf, width=420, height=320, bg="white")
        c.pack()
        tam, x0, y0 = 50, 60, 20
        for i in range(5):
            for p in range(5):
                pts = (p + 1) * (i + 1)
                color = COLOR_NIVEL["bajo" if pts < 5 else "medio" if pts < 10 else "alto" if pts < 17 else "crítico"]
                x, y = x0 + p * tam, y0 + (4 - i) * tam
                c.create_rectangle(x, y, x + tam, y + tam, fill=color, outline="white")
                if m[i][p]:
                    c.create_text(x + tam / 2, y + tam / 2, text=str(m[i][p]), font=("Segoe UI", 14, "bold"))
        for k in range(5):
            c.create_text(x0 + k * tam + tam / 2, y0 + 5 * tam + 12, text=str(k + 1))
            c.create_text(x0 - 14, y0 + (4 - k) * tam + tam / 2, text=str(k + 1))
        c.create_text(x0 + 2.5 * tam, y0 + 5 * tam + 30, text="Probabilidad")
        c.create_text(18, y0 + 2.5 * tam, text="Impacto", angle=90)
