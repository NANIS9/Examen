"""Pestaña 2: Control de acceso. Formulario P/Q/R/S(+V,H) o búsqueda por placa; semáforo y explicación."""
import tkinter as tk
from tkinter import ttk, messagebox

from ..reglas import decidir, premisas_desde_camion, PREMISAS
from .base import Contexto, Semaforo, etiqueta_titulo, texto_scroll, set_texto, mostrar_error, COLORES


class ControlAcceso(ttk.Frame):
    def __init__(self, master, ctx: Contexto):
        super().__init__(master, padding=12)
        self.ctx = ctx
        etiqueta_titulo(self, "Control de acceso")

        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill="both", expand=True)
        izq = ttk.Frame(cuerpo)
        izq.pack(side="left", fill="y", padx=(0, 16))

        # --- Búsqueda por placa / camión ------------------------------------------
        b = ttk.Labelframe(izq, text="Buscar camión registrado", padding=8)
        b.pack(fill="x")
        ttk.Label(b, text="Placa o ID (ej. ABC-123-D / CAM-102):").grid(row=0, column=0, columnspan=2, sticky="w")
        self.e_busqueda = ttk.Entry(b, width=22)
        self.e_busqueda.grid(row=1, column=0, pady=4)
        self.e_busqueda.bind("<Return>", lambda _e: self.buscar())
        ttk.Button(b, text="Buscar", command=self.buscar).grid(row=1, column=1, padx=4)
        ttk.Label(b, text="Peso en báscula (kg, opcional):").grid(row=2, column=0, columnspan=2, sticky="w")
        self.e_peso = ttk.Entry(b, width=22)
        self.e_peso.grid(row=3, column=0, pady=4, sticky="w")
        self.lbl_camion = ttk.Label(b, text="", foreground="#555", wraplength=260, justify="left")
        self.lbl_camion.grid(row=4, column=0, columnspan=2, sticky="w")

        # --- Formulario manual --------------------------------------------------------
        f = ttk.Labelframe(izq, text="Premisas (manual)", padding=8)
        f.pack(fill="x", pady=10)
        self.vars = {}
        defectos = {"P": True, "Q": False, "R": False, "S": True, "V": True, "H": True}
        for i, (letra, desc) in enumerate(PREMISAS.items()):
            var = tk.BooleanVar(value=defectos[letra])
            self.vars[letra] = var
            ttk.Checkbutton(f, text=f"{letra}: {desc}", variable=var).grid(row=i, column=0, sticky="w")
        ttk.Button(f, text="Evaluar", command=self.evaluar_manual).grid(row=len(PREMISAS), column=0, pady=(8, 0), sticky="w")

        self.camion_actual = None

        # --- Resultado -----------------------------------------------------------------
        der = ttk.Frame(cuerpo)
        der.pack(side="left", fill="both", expand=True)
        res = ttk.Frame(der)
        res.pack(fill="x")
        self.semaforo = Semaforo(res)
        self.semaforo.pack(side="left", padx=(0, 16))
        self.lbl_decision = tk.Label(res, text="Sin evaluar", font=("Segoe UI", 20, "bold"), fg=COLORES["gris"])
        self.lbl_decision.pack(anchor="w")
        self.lbl_causa = ttk.Label(res, text="", wraplength=520, justify="left")
        self.lbl_causa.pack(anchor="w", pady=4)
        self.btn_guardar = ttk.Button(res, text="Guardar en bitácora (accesos)", command=self.guardar, state="disabled")
        self.btn_guardar.pack(anchor="w", pady=6)

        ttk.Label(der, text="Explicación paso a paso:", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        self.txt = texto_scroll(der, alto=16)
        self.txt.configure(state="disabled")
        self.ultima_decision = None

    # ------------------------------------------------------------------
    def _leer_peso(self):
        t = self.e_peso.get().strip().replace(",", "")
        if not t:
            return None
        try:
            peso = float(t)
        except ValueError:
            raise ValueError(f"El peso debe ser un número en kilogramos (recibí '{t}').")
        if peso <= 0 or peso > 200000:
            raise ValueError("El peso debe estar entre 1 y 200,000 kg.")
        return peso

    def buscar(self):
        ident = self.e_busqueda.get().strip().upper()
        if not ident:
            mostrar_error("Búsqueda", "Escribe una placa o un ID de camión.")
            return
        try:
            peso = self._leer_peso()
            cam = self.ctx.repos.camiones.por_placa(ident) or self.ctx.repos.camiones.por_camion_id(ident)
        except ValueError as exc:
            mostrar_error("Dato inválido", str(exc))
            return
        except Exception as exc:
            mostrar_error("Base de datos", f"No se pudo consultar la colección camiones:\n{exc}")
            return
        if not cam:
            self.lbl_camion.configure(text=f"No existe '{ident}' en la colección camiones. Puedes evaluarlo con "
                                           "el formulario manual (P = F) o registrarlo en la pestaña Camiones.")
            self.camion_actual = None
            self._mostrar(decidir({"P": False, "Q": False, "R": False, "S": False}))
            return
        self.camion_actual = cam
        cond = cam.get("conductor", {})
        self.lbl_camion.configure(text=f"{cam['camion_id']} | {cam['placa']} | {cam.get('empresa')}\n"
                                       f"Conductor: {cond.get('nombre')} | Cert: {cond.get('certificacion') or 'NO'} "
                                       f"vigente hasta {cond.get('vigente_hasta') or '-'}\n"
                                       f"Autorizado: {cam.get('autorizacion')} | Peligrosos: {cam.get('materiales_peligrosos')} "
                                       f"| Peso registrado: {cam.get('peso_bruto_kg')} kg")
        cfg = self.ctx.config
        premisas = premisas_desde_camion(cam, peso, cfg.peso_maximo_kg, hora_inicio=cfg.hora_inicio_peligrosos,
                                         hora_fin=cfg.hora_fin_peligrosos)
        for k, v in premisas.items():
            self.vars[k].set(v)
        self._mostrar(decidir(premisas), peso)

    def evaluar_manual(self):
        self.camion_actual = None
        self._mostrar(decidir({k: v.get() for k, v in self.vars.items()}))

    def _mostrar(self, decision, peso=None):
        self.ultima_decision = dict(decision, peso_kg=peso)
        textos = {"ACCESO_ESTANDAR": "ACCESO ESTÁNDAR", "INSPECCION_ESPECIAL": "INSPECCIÓN ESPECIAL",
                  "DENEGADO": "ACCESO DENEGADO", "RETENIDO": "RETENIDO EN PATIO"}
        self.semaforo.encender(decision["semaforo"])
        self.lbl_decision.configure(text=textos[decision["decision"]], fg=COLORES[decision["semaforo"]])
        self.lbl_causa.configure(text=decision["causa"])
        set_texto(self.txt, "\n".join(decision["explicacion"]))
        self.btn_guardar.configure(state="normal")

    def guardar(self):
        if not self.ultima_decision:
            return
        d = dict(self.ultima_decision)
        cam = self.camion_actual or {}
        try:
            _id = self.ctx.repos.accesos.registrar(d, self.ctx.operador, placa=cam.get("placa"),
                                                   camion_id=cam.get("camion_id"))
        except Exception as exc:
            mostrar_error("Base de datos", f"No se pudo guardar el acceso:\n{exc}")
            return
        messagebox.showinfo("Bitácora", f"Acceso guardado en la colección 'accesos' con id {_id}.")
        self.ctx.notificar()
