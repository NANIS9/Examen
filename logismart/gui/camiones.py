"""Pestaña: CRUD de la colección camiones."""
import re
import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox

from .base import Contexto, Tabla, etiqueta_titulo, mostrar_error


class CamionesGUI(ttk.Frame):
    def __init__(self, master, ctx: Contexto):
        super().__init__(master, padding=12)
        self.ctx = ctx
        etiqueta_titulo(self, "Camiones (colección camiones)")
        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill="both", expand=True)

        form = ttk.Labelframe(cuerpo, text="Alta / edición", padding=8)
        form.pack(side="left", fill="y", padx=(0, 12))
        self.campos = {}
        etiquetas = [("camion_id", "ID camión (CAM-###)"), ("placa", "Placa (ABC-123-D)"), ("empresa", "Empresa"),
                     ("peso_bruto_kg", "Peso bruto (kg)"), ("nombre", "Conductor"), ("certificacion", "No. certificación"),
                     ("vigente_hasta", "Vigente hasta (AAAA-MM-DD)")]
        for i, (k, t) in enumerate(etiquetas):
            ttk.Label(form, text=t).grid(row=i, column=0, sticky="w", pady=2)
            e = ttk.Entry(form, width=26)
            e.grid(row=i, column=1, pady=2)
            self.campos[k] = e
        self.v_aut = tk.BooleanVar(value=True)
        self.v_pel = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Autorización previa", variable=self.v_aut).grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(form, text="Transporta materiales peligrosos", variable=self.v_pel).grid(row=8, column=0, columnspan=2, sticky="w")
        botones = ttk.Frame(form)
        botones.grid(row=9, column=0, columnspan=2, pady=8, sticky="w")
        ttk.Button(botones, text="Crear", command=self.crear).pack(side="left")
        ttk.Button(botones, text="Guardar cambios", command=self.actualizar).pack(side="left", padx=4)
        ttk.Button(botones, text="Eliminar", command=self.eliminar).pack(side="left")
        ttk.Button(botones, text="Limpiar", command=self.limpiar).pack(side="left", padx=4)
        self._id = None

        der = ttk.Frame(cuerpo)
        der.pack(side="left", fill="both", expand=True)
        fila = ttk.Frame(der)
        fila.pack(fill="x")
        ttk.Label(fila, text="Buscar:").pack(side="left")
        self.e_buscar = ttk.Entry(fila, width=24)
        self.e_buscar.pack(side="left", padx=4)
        self.e_buscar.bind("<KeyRelease>", lambda _e: self.refrescar())
        self.tabla = Tabla(der, [("camion_id", "ID", 80), ("placa", "Placa", 95), ("empresa", "Empresa", 160),
                                 ("aut", "Aut.", 45), ("pel", "Pelig.", 50), ("peso", "Peso kg", 70),
                                 ("conductor", "Conductor", 120), ("vig", "Cert. vigente hasta", 120)], alto=18)
        self.tabla.pack(fill="both", expand=True, pady=6)
        self.tabla.al_seleccionar(self.cargar)
        ctx.suscribir(self.refrescar)
        self.refrescar()

    def _leer(self):
        v = {k: e.get().strip() for k, e in self.campos.items()}
        if not re.fullmatch(r"CAM-\d{1,4}", v["camion_id"].upper()):
            raise ValueError("El ID debe tener el formato CAM-### (ejemplo CAM-102).")
        if not re.fullmatch(r"[A-Z0-9]{2,3}-\d{2,3}-[A-Z0-9]{1,2}", v["placa"].upper()):
            raise ValueError("La placa debe tener el formato ABC-123-D.")
        if not v["empresa"]:
            raise ValueError("La empresa es obligatoria.")
        try:
            peso = float(v["peso_bruto_kg"] or 0)
        except ValueError:
            raise ValueError("El peso debe ser numérico (kg).")
        if peso < 0 or peso > 200000:
            raise ValueError("El peso debe estar entre 0 y 200,000 kg.")
        if v["vigente_hasta"]:
            try:
                date.fromisoformat(v["vigente_hasta"])
            except ValueError:
                raise ValueError("La vigencia debe tener formato AAAA-MM-DD.")
        return {"camion_id": v["camion_id"].upper(), "placa": v["placa"].upper(), "empresa": v["empresa"],
                "peso_bruto_kg": peso, "autorizacion": self.v_aut.get(), "materiales_peligrosos": self.v_pel.get(),
                "conductor": {"nombre": v["nombre"], "certificacion": v["certificacion"] or None,
                              "vigente_hasta": v["vigente_hasta"] or None}}

    def crear(self):
        try:
            _id = self.ctx.repos.camiones.crear(self._leer())
        except ValueError as exc:
            mostrar_error("Validación", str(exc))
            return
        except Exception as exc:
            mostrar_error("Base de datos", f"No se pudo crear el camión:\n{exc}")
            return
        messagebox.showinfo("Camiones", f"Camión creado (id {_id}).")
        self.limpiar()
        self.ctx.notificar()

    def actualizar(self):
        if not self._id:
            mostrar_error("Camiones", "Selecciona un camión de la tabla para editarlo.")
            return
        try:
            self.ctx.repos.camiones.actualizar(self._id, self._leer())
        except ValueError as exc:
            mostrar_error("Validación", str(exc))
            return
        except Exception as exc:
            mostrar_error("Base de datos", str(exc))
            return
        self.ctx.notificar()

    def eliminar(self):
        if not self._id:
            mostrar_error("Camiones", "Selecciona un camión de la tabla.")
            return
        if messagebox.askyesno("Eliminar", "¿Eliminar el camión seleccionado?"):
            self.ctx.repos.camiones.eliminar(self._id)
            self.limpiar()
            self.ctx.notificar()

    def limpiar(self):
        self._id = None
        for e in self.campos.values():
            e.delete(0, "end")
        self.v_aut.set(True)
        self.v_pel.set(False)

    def cargar(self, d):
        self._id = d["_id"]
        c = d.get("conductor", {}) or {}
        valores = {"camion_id": d["camion_id"], "placa": d["placa"], "empresa": d.get("empresa", ""),
                   "peso_bruto_kg": d.get("peso_bruto_kg", ""), "nombre": c.get("nombre", ""),
                   "certificacion": c.get("certificacion") or "", "vigente_hasta": c.get("vigente_hasta") or ""}
        for k, e in self.campos.items():
            e.delete(0, "end")
            e.insert(0, str(valores[k]))
        self.v_aut.set(bool(d.get("autorizacion")))
        self.v_pel.set(bool(d.get("materiales_peligrosos")))

    def refrescar(self):
        try:
            docs = self.ctx.repos.camiones.buscar(self.e_buscar.get())
        except Exception as exc:
            mostrar_error("Base de datos", f"No se pudo leer la colección camiones:\n{exc}")
            return
        self.tabla.llenar([(d["camion_id"], d["placa"], d.get("empresa", ""), "Sí" if d.get("autorizacion") else "No",
                            "Sí" if d.get("materiales_peligrosos") else "No", d.get("peso_bruto_kg", ""),
                            (d.get("conductor") or {}).get("nombre", ""), (d.get("conductor") or {}).get("vigente_hasta") or "-")
                           for d in docs], docs)
