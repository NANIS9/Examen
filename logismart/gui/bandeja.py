"""Pestaña 4: Bandeja de incidentes. Pegar correo -> clasificar (híbrido) -> editar -> cambiar estado -> historial."""
import json
import tkinter as tk
from tkinter import ttk, messagebox

from ..clasificador import CATEGORIAS_VALIDAS, PRIORIDADES
from ..db.repositorios import ESTADOS_INCIDENTE
from .base import Contexto, Tabla, Cargando, etiqueta_titulo, texto_scroll, set_texto, mostrar_error, fmt_fecha, en_hilo


class BandejaIncidentes(ttk.Frame):
    def __init__(self, master, ctx: Contexto):
        super().__init__(master, padding=12)
        self.ctx = ctx
        etiqueta_titulo(self, "Bandeja de incidentes")
        cuerpo = ttk.Panedwindow(self, orient="horizontal")
        cuerpo.pack(fill="both", expand=True)

        # --- Izquierda: nuevo correo ---------------------------------------------
        izq = ttk.Labelframe(cuerpo, text="Nuevo correo", padding=8)
        cuerpo.add(izq, weight=1)
        ttk.Label(izq, text="Remitente:").pack(anchor="w")
        self.e_rem = ttk.Entry(izq)
        self.e_rem.pack(fill="x")
        ttk.Label(izq, text="Asunto:").pack(anchor="w", pady=(6, 0))
        self.e_asunto = ttk.Entry(izq)
        self.e_asunto.pack(fill="x")
        ttk.Label(izq, text="Cuerpo (pega aquí el correo):").pack(anchor="w", pady=(6, 0))
        self.t_cuerpo = tk.Text(izq, height=8, wrap="word")
        self.t_cuerpo.pack(fill="both", expand=True)
        fila = ttk.Frame(izq)
        fila.pack(fill="x", pady=6)
        self.usar_llm = tk.BooleanVar(value=True)
        ttk.Checkbutton(fila, text="Usar LLM (híbrido)", variable=self.usar_llm).pack(side="left")
        self.btn_clasificar = ttk.Button(fila, text="Clasificar", command=self.clasificar)
        self.btn_clasificar.pack(side="left", padx=8)
        ttk.Button(fila, text="Ejemplo", command=self._ejemplo).pack(side="left")
        self.cargando = Cargando(izq, "Clasificando con el LLM...")

        # --- Resultado editable ------------------------------------------------------
        res = ttk.Labelframe(izq, text="Resultado (editable antes de guardar)", padding=8)
        res.pack(fill="x")
        ttk.Label(res, text="Categoría:").grid(row=0, column=0, sticky="w")
        self.cb_cat = ttk.Combobox(res, values=CATEGORIAS_VALIDAS, state="readonly", width=24)
        self.cb_cat.grid(row=0, column=1, sticky="w")
        ttk.Label(res, text="Prioridad:").grid(row=1, column=0, sticky="w")
        self.cb_pri = ttk.Combobox(res, values=PRIORIDADES, state="readonly", width=24)
        self.cb_pri.grid(row=1, column=1, sticky="w")
        self.lbl_fuente = ttk.Label(res, text="", foreground="#555", wraplength=330, justify="left")
        self.lbl_fuente.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        self.t_res = tk.Text(res, height=6, wrap="word", font=("Consolas", 9))
        self.t_res.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.btn_guardar = ttk.Button(res, text="Guardar incidente", command=self.guardar, state="disabled")
        self.btn_guardar.grid(row=4, column=0, columnspan=2, pady=6, sticky="w")
        res.columnconfigure(1, weight=1)
        self.resultado = None

        # --- Derecha: lista + detalle ----------------------------------------------------
        der = ttk.Frame(cuerpo, padding=(8, 0, 0, 0))
        cuerpo.add(der, weight=2)
        filtros = ttk.Frame(der)
        filtros.pack(fill="x")
        ttk.Label(filtros, text="Estado:").pack(side="left")
        self.cb_filtro = ttk.Combobox(filtros, values=("todos",) + ESTADOS_INCIDENTE, state="readonly", width=12)
        self.cb_filtro.set("todos")
        self.cb_filtro.pack(side="left", padx=4)
        self.cb_filtro.bind("<<ComboboxSelected>>", lambda _e: self.refrescar())
        ttk.Button(filtros, text="Actualizar", command=self.refrescar).pack(side="left", padx=4)
        self.tabla = Tabla(der, [("fecha", "Fecha", 110), ("prioridad", "Prioridad", 70), ("categoria", "Categoría", 150),
                                 ("estado", "Estado", 85), ("rev", "Rev.", 40), ("asunto", "Asunto", 220)], alto=10)
        self.tabla.pack(fill="both", expand=True, pady=6)
        self.tabla.tree.tag_configure("critica", background="#ffd6d6")
        self.tabla.tree.tag_configure("alta", background="#ffe9c7")
        self.tabla.al_seleccionar(self.mostrar_detalle)

        acciones = ttk.Frame(der)
        acciones.pack(fill="x")
        ttk.Label(acciones, text="Cambiar estado a:").pack(side="left")
        for est in ESTADOS_INCIDENTE:
            ttk.Button(acciones, text=est, command=lambda e=est: self.cambiar_estado(e)).pack(side="left", padx=2)
        ttk.Button(acciones, text="Guardar edición", command=self.editar_seleccionado).pack(side="left", padx=(12, 2))
        ttk.Button(acciones, text="Eliminar", command=self.eliminar).pack(side="left", padx=2)

        ttk.Label(der, text="Detalle e historial:", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 0))
        self.t_detalle = texto_scroll(der, alto=10)
        self.t_detalle.configure(state="disabled")

        ctx.suscribir(self.refrescar)
        self.refrescar()

    # ------------------------------------------------------------------
    def _ejemplo(self):
        self.e_rem.delete(0, "end"); self.e_rem.insert(0, "operador.caseta@logismart.example")
        self.e_asunto.delete(0, "end"); self.e_asunto.insert(0, "URGENTE: derrame en andén 3")
        self.t_cuerpo.delete("1.0", "end")
        self.t_cuerpo.insert("1.0", "El camión CAM-102 con placas ABC-123-D presenta una fuga de químico inflamable. "
                                    "La báscula marcó 48.5 toneladas. Se requiere apoyo inmediato.")

    def _leer_correo(self):
        rem, asunto, cuerpo = self.e_rem.get().strip(), self.e_asunto.get().strip(), self.t_cuerpo.get("1.0", "end").strip()
        if not asunto and not cuerpo:
            raise ValueError("Escribe al menos el asunto o el cuerpo del correo.")
        if len(cuerpo) > 5000:
            raise ValueError("El cuerpo es demasiado largo (máximo 5000 caracteres).")
        return {"remitente": rem or "desconocido", "asunto": asunto, "cuerpo": cuerpo}

    def clasificar(self):
        try:
            correo = self._leer_correo()
        except ValueError as exc:
            mostrar_error("Validación", str(exc))
            return
        self.btn_clasificar.configure(state="disabled")
        self.cargando.iniciar("Clasificando con el LLM..." if self.usar_llm.get() else "Clasificando por reglas...")
        self.ctx.clasificador.usar_llm = self.usar_llm.get()

        def listo(res):
            self.cargando.detener()
            self.btn_clasificar.configure(state="normal")
            self.resultado = res
            self.cb_cat.set(res["categoria"])
            self.cb_pri.set(res["prioridad"])
            d = res["detalle"]
            txt = f"Fuente: {res['fuente']}"
            if res["requiere_revision_humana"]:
                txt += "  |  REQUIERE REVISIÓN HUMANA (LLM y reglas discrepan)"
            if d["error_llm"]:
                txt += f"\nLLM no disponible -> respaldo por reglas. {d['error_llm'][:120]}"
            elif d["llm"]:
                txt += f"\nLLM: {d['llm']['categoria']}/{d['llm']['prioridad']} ({d['llm']['latencia_ms']} ms, {d['llm']['intentos']} intento(s))"
                txt += f"   Reglas: {d['reglas']['categoria']}/{d['reglas']['prioridad']}"
            self.lbl_fuente.configure(text=txt)
            self.t_res.delete("1.0", "end")
            self.t_res.insert("1.0", f"Resumen: {res['resumen']}\nEntidades: {json.dumps(res['entidades'], ensure_ascii=False)}")
            self.btn_guardar.configure(state="normal")

        def fallo(exc):
            self.cargando.detener()
            self.btn_clasificar.configure(state="normal")
            mostrar_error("Clasificación", f"No se pudo clasificar el correo:\n{exc}")

        en_hilo(self, lambda: self.ctx.clasificador.clasificar(correo["asunto"], correo["cuerpo"], correo["remitente"]),
                listo, fallo)

    def guardar(self):
        if not self.resultado:
            return
        try:
            correo = self._leer_correo()
        except ValueError as exc:
            mostrar_error("Validación", str(exc))
            return
        clasif = {k: self.resultado[k] for k in ("entidades", "resumen", "fuente", "requiere_revision_humana", "detalle")}
        clasif["categoria"], clasif["prioridad"] = self.cb_cat.get(), self.cb_pri.get()
        if (clasif["categoria"], clasif["prioridad"]) != (self.resultado["categoria"], self.resultado["prioridad"]):
            clasif["editado_por_operador"] = True
        try:
            _id = self.ctx.repos.incidentes.registrar(correo, clasif, self.resultado["entidades"], self.ctx.operador)
        except Exception as exc:
            mostrar_error("Base de datos", f"No se pudo guardar el incidente:\n{exc}")
            return
        messagebox.showinfo("Incidente", f"Incidente guardado con id {_id}.")
        self.resultado = None
        self.btn_guardar.configure(state="disabled")
        self.ctx.notificar()

    # ------------------------------------------------------------------
    def refrescar(self):
        estado = self.cb_filtro.get()
        try:
            docs = self.ctx.repos.incidentes.recientes(limite=200, estado=None if estado == "todos" else estado)
        except Exception as exc:
            mostrar_error("Base de datos", f"No se pudo leer la colección incidentes:\n{exc}")
            return
        filas = [(fmt_fecha(d["fecha"]), d["clasificacion"]["prioridad"], d["clasificacion"]["categoria"], d["estado"],
                  "SÍ" if d["clasificacion"].get("requiere_revision_humana") else "", d["correo"]["asunto"][:60]) for d in docs]
        self.tabla.llenar(filas, docs, tags=[d["clasificacion"]["prioridad"] for d in docs])

    def mostrar_detalle(self, d):
        c = d["clasificacion"]
        self.cb_cat.set(c["categoria"])
        self.cb_pri.set(c["prioridad"])
        L = [f"ID: {d['_id']}    Estado: {d['estado']}    Fecha: {fmt_fecha(d['fecha'])}",
             f"De: {d['correo']['remitente']}", f"Asunto: {d['correo']['asunto']}", "", d["correo"]["cuerpo"], "",
             f"Clasificación: {c['categoria']} / {c['prioridad']}  (fuente: {c.get('fuente')}, "
             f"revisión humana: {c.get('requiere_revision_humana')})",
             f"Resumen: {c.get('resumen')}", f"Entidades: {json.dumps(d.get('datos_extraidos'), ensure_ascii=False)}", "",
             "Historial:"]
        L += [f"  {fmt_fecha(h['fecha'])}  {h['accion']}  ({h.get('operador')})" for h in d.get("historial", [])]
        set_texto(self.t_detalle, "\n".join(L))

    def cambiar_estado(self, estado):
        d = self.tabla.seleccionado()
        if not d:
            mostrar_error("Incidentes", "Selecciona un incidente de la lista.")
            return
        try:
            self.ctx.repos.incidentes.cambiar_estado(d["_id"], estado, self.ctx.operador)
        except Exception as exc:
            mostrar_error("Base de datos", str(exc))
            return
        self.ctx.notificar()

    def editar_seleccionado(self):
        d = self.tabla.seleccionado()
        if not d:
            mostrar_error("Incidentes", "Selecciona un incidente de la lista para editar su categoría/prioridad.")
            return
        clasif = dict(d["clasificacion"], categoria=self.cb_cat.get(), prioridad=self.cb_pri.get(), editado_por_operador=True)
        try:
            self.ctx.repos.incidentes.editar_clasificacion(d["_id"], clasif, self.ctx.operador)
        except Exception as exc:
            mostrar_error("Base de datos", str(exc))
            return
        self.ctx.notificar()

    def eliminar(self):
        d = self.tabla.seleccionado()
        if not d:
            mostrar_error("Incidentes", "Selecciona un incidente de la lista.")
            return
        if messagebox.askyesno("Eliminar", f"¿Eliminar el incidente '{d['correo']['asunto'][:40]}'?"):
            self.ctx.repos.incidentes.eliminar(d["_id"])
            self.ctx.notificar()
