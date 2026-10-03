"""
Utilidades compartidas por todas las pestañas de la GUI:
  - Contexto: servicios compartidos (repos, LLM, clasificador, asistente, riesgos) + notificación de cambios
  - en_hilo(): ejecuta trabajo pesado (LLM, Mongo) fuera del hilo de tkinter y devuelve al hilo principal
  - Semaforo, Tabla, Cargando: widgets reutilizables
  - parse_fecha(): validación de fechas con mensaje claro
"""
import queue
import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk, messagebox
from typing import Callable, Dict, List, Optional

COLORES = {"verde": "#2e9e4f", "amarillo": "#e3b505", "rojo": "#d64545", "gris": "#9a9a9a"}
FUENTE_TITULO = ("Segoe UI", 14, "bold")
FUENTE_SUB = ("Segoe UI", 10, "bold")
FUENTE_MONO = ("Consolas", 10)


class Contexto:
    """Servicios compartidos entre pestañas."""

    def __init__(self, repos, llm, clasificador, asistente, riesgos, config):
        self.repos, self.llm, self.clasificador = repos, llm, clasificador
        self.asistente, self.riesgos, self.config = asistente, riesgos, config
        self._oyentes: List[Callable[[], None]] = []
        self.ollama_estado: tuple = (False, "sin verificar")

    @property
    def operador(self) -> str:
        return self.config.operador

    def suscribir(self, fn: Callable[[], None]) -> None:
        self._oyentes.append(fn)

    def notificar(self) -> None:
        for fn in self._oyentes:
            try:
                fn()
            except Exception as exc:          # una pestaña con error no debe tumbar a las demás
                print(f"[GUI] error al refrescar: {exc}")


_cola_gui: "queue.Queue[tuple]" = queue.Queue()


def despachar(fn: Callable, arg=None) -> None:
    """Encola una llamada para que se ejecute en el hilo principal de tkinter (seguro desde cualquier hilo)."""
    _cola_gui.put((fn, arg))


def bombear(raiz: tk.Misc, intervalo_ms: int = 40) -> None:
    """Procesa la cola de llamadas pendientes; se reprograma a sí misma con after()."""
    try:
        while True:
            fn, arg = _cola_gui.get_nowait()
            try:
                fn(arg)
            except Exception as exc:
                print(f"[GUI] error en callback: {exc}")
    except queue.Empty:
        pass
    raiz.after(intervalo_ms, bombear, raiz, intervalo_ms)


def en_hilo(widget: tk.Misc, trabajo: Callable, al_terminar: Callable, al_fallar: Optional[Callable] = None) -> None:
    """Ejecuta `trabajo()` en un hilo; el resultado se entrega a `al_terminar(resultado)` en el hilo de tkinter."""
    def _run():
        try:
            resultado = trabajo()
        except Exception as exc:
            despachar(al_fallar or (lambda e: mostrar_error("Error", str(e))), exc)
            return
        despachar(al_terminar, resultado)
    threading.Thread(target=_run, daemon=True).start()


def mostrar_error(titulo: str, mensaje: str) -> None:
    messagebox.showerror(titulo, mensaje)


def parse_fecha(texto: str, fin_del_dia: bool = False) -> Optional[datetime]:
    """Convierte 'AAAA-MM-DD' en datetime; vacío -> None; inválido -> ValueError con mensaje claro."""
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        d = datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Fecha inválida: '{texto}'. Usa el formato AAAA-MM-DD (ejemplo 2026-10-03).")
    return d + timedelta(hours=23, minutes=59, seconds=59) if fin_del_dia else d


def fmt_fecha(v) -> str:
    return v.strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime) else (str(v) if v else "")


class Semaforo(tk.Canvas):
    """Tres luces verticales; `encender('verde'|'amarillo'|'rojo'|None)`."""

    def __init__(self, master, tam: int = 36, **kw):
        super().__init__(master, width=tam + 16, height=3 * tam + 24, bg="#333", highlightthickness=0, **kw)
        self.tam = tam
        self._luces = {}
        for i, color in enumerate(("rojo", "amarillo", "verde")):
            y = 8 + i * (tam + 4)
            self._luces[color] = self.create_oval(8, y, 8 + tam, y + tam, fill="#555", outline="#222")
        self.encender(None)

    def encender(self, color: Optional[str]) -> None:
        for c, item in self._luces.items():
            self.itemconfigure(item, fill=COLORES[c] if c == color else "#555")


class Tabla(ttk.Frame):
    """Treeview con barra de desplazamiento y columnas configurables. Guarda el doc de cada fila."""

    def __init__(self, master, columnas: List[tuple], alto: int = 12, **kw):
        super().__init__(master, **kw)
        ids = [c[0] for c in columnas]
        self.tree = ttk.Treeview(self, columns=ids, show="headings", height=alto, selectmode="browse")
        for cid, titulo, ancho in columnas:
            self.tree.heading(cid, text=titulo)
            self.tree.column(cid, width=ancho, anchor="w", stretch=True)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._docs: Dict[str, Dict] = {}

    def llenar(self, filas: List[tuple], docs: Optional[List[Dict]] = None, tags: Optional[List[str]] = None) -> None:
        self.tree.delete(*self.tree.get_children())
        self._docs.clear()
        for i, fila in enumerate(filas):
            iid = self.tree.insert("", "end", values=fila, tags=(tags[i],) if tags else ())
            if docs:
                self._docs[iid] = docs[i]

    def seleccionado(self) -> Optional[Dict]:
        sel = self.tree.selection()
        return self._docs.get(sel[0]) if sel else None

    def al_seleccionar(self, fn: Callable[[Dict], None]) -> None:
        self.tree.bind("<<TreeviewSelect>>", lambda _e: (lambda d: fn(d) if d else None)(self.seleccionado()))


class Cargando(ttk.Frame):
    """Indicador de actividad (barra indeterminada + texto) que se muestra mientras responde el LLM o Mongo."""

    def __init__(self, master, texto: str = "Procesando...", **kw):
        super().__init__(master, **kw)
        self.var = tk.StringVar(value=texto)
        self.barra = ttk.Progressbar(self, mode="indeterminate", length=160)
        self.barra.pack(side="left", padx=(0, 8))
        ttk.Label(self, textvariable=self.var, foreground="#555").pack(side="left")

    def iniciar(self, texto: Optional[str] = None) -> None:
        if texto:
            self.var.set(texto)
        self.pack(fill="x", pady=4)
        self.barra.start(12)

    def detener(self) -> None:
        self.barra.stop()
        self.pack_forget()


def etiqueta_titulo(master, texto: str) -> ttk.Label:
    lbl = ttk.Label(master, text=texto, font=FUENTE_TITULO)
    lbl.pack(anchor="w", pady=(6, 10))
    return lbl


def texto_scroll(master, alto: int = 10, **kw) -> tk.Text:
    marco = ttk.Frame(master)
    marco.pack(fill="both", expand=True, **kw)
    txt = tk.Text(marco, height=alto, wrap="word", font=FUENTE_MONO)
    sb = ttk.Scrollbar(marco, command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    txt.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return txt


def set_texto(txt: tk.Text, contenido: str) -> None:
    estado = txt.cget("state")
    txt.configure(state="normal")
    txt.delete("1.0", "end")
    txt.insert("1.0", contenido)
    txt.configure(state=estado)
