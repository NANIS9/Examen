"""Pestaña 3: Simulador de tablas de verdad. Interruptores en vivo + tablas + análisis de reglas."""
import tkinter as tk
from tkinter import ttk

from ..reglas import PREMISAS, REGLAS, evaluar, tabla_texto, generar_tabla_verdad, analizar_reglas
from .base import Contexto, etiqueta_titulo, texto_scroll, set_texto, COLORES, FUENTE_MONO


class Simulador(ttk.Frame):
    def __init__(self, master, ctx: Contexto):
        super().__init__(master, padding=12)
        etiqueta_titulo(self, "Simulador de tablas de verdad")

        arriba = ttk.Frame(self)
        arriba.pack(fill="x")

        # --- Interruptores ---------------------------------------------------------
        sw = ttk.Labelframe(arriba, text="Interruptores (cambian A y E en vivo)", padding=8)
        sw.pack(side="left", fill="y", padx=(0, 12))
        self.vars = {}
        for i, (letra, desc) in enumerate(PREMISAS.items()):
            var = tk.BooleanVar(value=letra in ("P", "S", "V", "H"))
            var.trace_add("write", lambda *_: self.actualizar())
            self.vars[letra] = var
            ttk.Checkbutton(sw, text=f"{letra}  {desc}", variable=var).grid(row=i, column=0, sticky="w", pady=2)

        # --- Salidas -----------------------------------------------------------------
        out = ttk.Labelframe(arriba, text="Resultado de las reglas", padding=8)
        out.pack(side="left", fill="both", expand=True)
        self.labels = {}
        for i, (letra, r) in enumerate(REGLAS.items()):
            ttk.Label(out, text=f"{letra} = {r['formula']}", font=FUENTE_MONO).grid(row=i, column=0, sticky="w", padx=(0, 12))
            ttk.Label(out, text=r["nombre"]).grid(row=i, column=1, sticky="w", padx=(0, 12))
            lbl = tk.Label(out, text="F", width=4, font=("Segoe UI", 14, "bold"), fg="white", bg=COLORES["gris"])
            lbl.grid(row=i, column=2, pady=2)
            self.labels[letra] = lbl
        self.lbl_inter = ttk.Label(out, text="", font=FUENTE_MONO, foreground="#555")
        self.lbl_inter.grid(row=len(REGLAS), column=0, columnspan=3, sticky="w", pady=(8, 0))

        # --- Tablas ---------------------------------------------------------------
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, pady=(12, 0))
        for letra in REGLAS:
            marco = ttk.Frame(nb, padding=6)
            nb.add(marco, text=f"Tabla {letra}")
            txt = texto_scroll(marco, alto=12)
            set_texto(txt, tabla_texto(letra) + "\n\n" + REGLAS_JUSTIFICACION.get(letra, ""))
            txt.configure(state="disabled")
        marco = ttk.Frame(nb, padding=6)
        nb.add(marco, text="Tabla completa (64)")
        txt = texto_scroll(marco, alto=12)
        set_texto(txt, self._tabla_completa())
        txt.configure(state="disabled")
        marco = ttk.Frame(nb, padding=6)
        nb.add(marco, text="Análisis de reglas")
        txt = texto_scroll(marco, alto=12)
        set_texto(txt, self._analisis())
        txt.configure(state="disabled")
        self.actualizar()

    def actualizar(self):
        p = {k: v.get() for k, v in self.vars.items()}
        r = evaluar(p)
        for letra, lbl in self.labels.items():
            lbl.configure(text="V" if r[letra] else "F", bg=COLORES["verde"] if r[letra] else COLORES["rojo"])
        v = lambda b: "V" if b else "F"
        self.lbl_inter.configure(text=f"Intermedias:  ¬Q={v(not p['Q'])}   P∧S={v(p['P'] and p['S'])}   "
                                      f"R∨Q={v(p['R'] or p['Q'])}   ¬V={v(not p['V'])}   ¬H={v(not p['H'])}")

    @staticmethod
    def _tabla_completa():
        v = lambda b: "V" if b else "F"
        enc = "  P   Q   R   S   V   H  |  ¬Q  P∧S  R∨Q |  A   E   B   X"
        L = [enc, "-" * len(enc)]
        for f in generar_tabla_verdad():
            L.append("  " + "   ".join(v(f[k]) for k in "PQRSVH") + "  |  " + f"{v(f['no_Q'])}    {v(f['P_y_S'])}    {v(f['R_o_Q'])}  |  "
                     + "   ".join(v(f[k]) for k in "AEBX"))
        return "\n".join(L)

    @staticmethod
    def _analisis():
        L = ["Detección automática de redundancias y contradicciones (64 combinaciones):", ""]
        for h in analizar_reglas():
            L.append(f"[{h['tipo']:<13}] {h['detalle']}")
        L += ["", "Interpretación:",
              "- 'implica' X → E: toda retención por horario también activa inspección (X ⊂ E). No es redundante",
              "  porque la ACCIÓN es distinta (retener vs inspeccionar); se resuelve con la prioridad X > E.",
              "- 'solapamiento' A y E (P∧S∧¬Q∧R): acceso estándar e inspección a la vez -> primero inspección.",
              "- 'solapamiento' A y B: conductor certificado pero vencido -> B bloquea aunque A sea verdadera.",
              "- No hay reglas equivalentes ni insatisfacibles: ninguna regla sobra."]
        return "\n".join(L)


REGLAS_JUSTIFICACION = {
    "A": "Regla original. Acceso estándar sólo con autorización previa, conductor certificado y peso dentro del límite.",
    "E": "Regla original. La inspección especial se activa con autorización y (materiales peligrosos o exceso de peso).",
    "B": "Regla NUEVA (vigencia de certificación). Un conductor con certificación VENCIDA (S ∧ ¬V) no debe operar aunque el\n"
         "camión esté autorizado. Se distingue de ¬S porque la respuesta operativa es renovar en ventanilla, no denegar\n"
         "permanentemente. Justificación: la NOM de transporte exige licencia/certificación vigente; una vencida no es válida.",
    "X": "Regla NUEVA (horario restringido para materiales peligrosos). Si R y la hora está fuera de la ventana permitida\n"
         "(¬H, por defecto 06:00-20:00) el camión se RETIENE en patio de espera. Justificación: en horario nocturno hay\n"
         "menos personal de emergencias y peor visibilidad; muchas instalaciones prohíben maniobrar peligrosos de noche.",
}
