# ============================================================
# PRACTICA 2
# TUTOR INTELIGENTE CON LLM  (versión con interfaz gráfica)
# ============================================================
#
# Objetivo: Implementación de un LLM.
#
#   1. Cambiar la configuración del sistema (rol distinto al del
#      ejercicio original: ahora es un "Chef y nutriólogo").
#   2. Interfaz gráfica (tkinter) para interactuar con el usuario.
#   3. Dar al usuario un breve resumen de su historial.
#
# Modelo: llama3.2 (ejecutado localmente con Ollama)
#
# Ejecución:
#   python p02primertutor_llm.py
#
# Requisitos:
#   pip install ollama
#   ollama pull llama3.2      (y tener Ollama en ejecución)
# ============================================================

# ------------------------------------------------------------
# 1. IMPORTAR BIBLIOTECAS
# ------------------------------------------------------------
import threading                      # Para no congelar la ventana mientras responde el LLM
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime

import ollama


# ------------------------------------------------------------
# 2. CONFIGURACIÓN DEL MODELO
# ------------------------------------------------------------
MODELO = "llama3.2"


# ------------------------------------------------------------
# 3. CONFIGURACIÓN DEL SISTEMA (rol distinto al ejemplo original)
# ------------------------------------------------------------
# El mensaje "system" define el comportamiento del asistente.
# En lugar del profesor de IA, ahora es un chef-nutriólogo.
# ------------------------------------------------------------
mensaje_sistema = """
Eres "Chef Sazón", un chef profesional de cocina mexicana que además
es nutriólogo certificado.

Tu función es ayudar a estudiantes universitarios con poco tiempo y
poco presupuesto a comer mejor.

Debes:
1. Proponer recetas sencillas, económicas y con ingredientes fáciles
   de conseguir en México.
2. Indicar siempre: ingredientes con cantidades, pasos numerados y
   tiempo aproximado de preparación.
3. Dar una estimación nutricional breve (calorías, proteína) y un
   consejo de salud por receta.
4. Adaptar las recetas si el usuario menciona alergias, dieta
   vegetariana/vegana o diabetes.
5. Responder siempre en español, con un tono amable y motivador.
6. Si la pregunta no es de cocina o nutrición, indicar con cortesía
   que solo puedes ayudar en esos temas.
"""


# ------------------------------------------------------------
# 4. HISTORIAL DE LA CONVERSACIÓN
# ------------------------------------------------------------
# Se conserva el contexto para que el modelo recuerde lo dicho.
# ------------------------------------------------------------
mensajes = [{"role": "system", "content": mensaje_sistema}]

# Bitácora paralela con hora de cada mensaje (para el resumen local)
bitacora = []


# ------------------------------------------------------------
# 5. FUNCIONES DE APOYO
# ------------------------------------------------------------
def consultar_llm(historial):
    """Envía el historial a Ollama y devuelve el texto de la respuesta."""
    respuesta = ollama.chat(model=MODELO, messages=historial)
    return respuesta["message"]["content"]


def resumen_local():
    """Resumen estadístico del historial calculado sin usar el LLM."""
    preguntas = [b for b in bitacora if b["rol"] == "user"]
    respuestas = [b for b in bitacora if b["rol"] == "assistant"]
    if not preguntas:
        return "Todavía no has hecho ninguna pregunta."
    inicio = preguntas[0]["hora"].strftime("%H:%M:%S")
    palabras = sum(len(p["texto"].split()) for p in preguntas)
    lineas = [
        f"Sesión iniciada a las {inicio}.",
        f"Preguntas realizadas: {len(preguntas)}",
        f"Respuestas recibidas: {len(respuestas)}",
        f"Palabras escritas por ti: {palabras}",
        "",
        "Tus preguntas:",
    ]
    for i, p in enumerate(preguntas, 1):
        texto = p["texto"] if len(p["texto"]) <= 70 else p["texto"][:67] + "..."
        lineas.append(f"  {i}. [{p['hora']:%H:%M}] {texto}")
    return "\n".join(lineas)


# ------------------------------------------------------------
# 6. INTERFAZ GRÁFICA
# ------------------------------------------------------------
class TutorGUI:
    """Ventana principal del tutor: área de chat, entrada y botones."""

    def __init__(self, raiz: tk.Tk):
        self.raiz = raiz
        raiz.title(f"Chef Sazón - Tutor con LLM ({MODELO})")
        raiz.geometry("760x600")
        raiz.minsize(600, 450)

        # --- Encabezado --------------------------------------------------
        encabezado = ttk.Frame(raiz, padding=8)
        encabezado.pack(fill="x")
        ttk.Label(encabezado, text="Chef Sazón: recetas y nutrición para estudiantes",
                  font=("Segoe UI", 13, "bold")).pack(side="left")
        self.estado = ttk.Label(encabezado, text="Listo", foreground="green")
        self.estado.pack(side="right")

        # --- Área de conversación -----------------------------------------
        self.chat = scrolledtext.ScrolledText(raiz, wrap="word", state="disabled",
                                              font=("Segoe UI", 10), padx=8, pady=8)
        self.chat.pack(fill="both", expand=True, padx=8)
        self.chat.tag_config("usuario", foreground="#1a4d8f", font=("Segoe UI", 10, "bold"))
        self.chat.tag_config("tutor", foreground="#8f3a1a", font=("Segoe UI", 10, "bold"))
        self.chat.tag_config("sistema", foreground="gray", font=("Segoe UI", 9, "italic"))

        # --- Entrada de texto + botones -----------------------------------
        panel = ttk.Frame(raiz, padding=8)
        panel.pack(fill="x")
        self.entrada = ttk.Entry(panel, font=("Segoe UI", 10))
        self.entrada.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entrada.bind("<Return>", lambda _e: self.enviar())
        self.entrada.focus()

        self.btn_enviar = ttk.Button(panel, text="Enviar", command=self.enviar)
        self.btn_enviar.pack(side="left")
        ttk.Button(panel, text="Resumen del historial", command=self.mostrar_resumen).pack(side="left", padx=6)
        ttk.Button(panel, text="Nueva sesión", command=self.reiniciar).pack(side="left")

        self.escribir("sistema", f"Modelo: {MODELO}. Escribe tu pregunta y presiona Enter.\n"
                                 "Ejemplo: '¿Qué puedo cenar con huevo, tortillas y frijoles?'")

    # ---------------------- utilidades de pantalla ---------------------------
    def escribir(self, quien: str, texto: str):
        """Agrega un bloque de texto al área de chat."""
        etiquetas = {"usuario": "Tú", "tutor": "Chef Sazón", "sistema": "Sistema"}
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{etiquetas[quien]}:\n", quien)
        self.chat.insert("end", texto.strip() + "\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def ocupado(self, valor: bool):
        """Deshabilita la entrada mientras el modelo responde (indicador de carga)."""
        self.btn_enviar.configure(state="disabled" if valor else "normal")
        self.entrada.configure(state="disabled" if valor else "normal")
        self.estado.configure(text="Pensando..." if valor else "Listo",
                              foreground="orange" if valor else "green")

    # ---------------------- acciones ----------------------------------------
    def enviar(self):
        pregunta = self.entrada.get().strip()
        if not pregunta:
            return
        self.entrada.delete(0, "end")
        self.escribir("usuario", pregunta)

        mensajes.append({"role": "user", "content": pregunta})
        bitacora.append({"rol": "user", "texto": pregunta, "hora": datetime.now()})
        self.ocupado(True)

        # El LLM puede tardar varios segundos: se consulta en un hilo aparte
        threading.Thread(target=self._pedir_respuesta, daemon=True).start()

    def _pedir_respuesta(self):
        try:
            contenido = consultar_llm(mensajes)
        except Exception as error:
            mensajes.pop()                      # La pregunta no se procesó: se retira del historial
            bitacora.pop()
            self.raiz.after(0, self._mostrar_error, str(error))
            return
        mensajes.append({"role": "assistant", "content": contenido})
        bitacora.append({"rol": "assistant", "texto": contenido, "hora": datetime.now()})
        # Las actualizaciones de tkinter deben hacerse desde el hilo principal
        self.raiz.after(0, self._mostrar_respuesta, contenido)

    def _mostrar_respuesta(self, contenido: str):
        self.escribir("tutor", contenido)
        self.ocupado(False)
        self.entrada.focus()

    def _mostrar_error(self, detalle: str):
        self.ocupado(False)
        self.escribir("sistema", "ERROR AL CONECTARSE CON EL LLM. Verifica que Ollama esté "
                                 f"ejecutándose y que el modelo '{MODELO}' esté descargado.\n{detalle}")
        messagebox.showerror("Sin conexión con Ollama",
                             "No se pudo obtener respuesta.\n\nAbre una terminal y ejecuta:\n"
                             f"   ollama serve\n   ollama pull {MODELO}")

    def mostrar_resumen(self):
        """Resumen del historial: estadísticas locales + resumen redactado por el LLM."""
        texto_local = resumen_local()
        self.escribir("sistema", "RESUMEN DE TU HISTORIAL\n" + texto_local)
        if len(bitacora) < 2:
            return
        self.ocupado(True)
        threading.Thread(target=self._resumen_llm, daemon=True).start()

    def _resumen_llm(self):
        # Se pide el resumen con una copia del historial para no contaminar la conversación
        peticion = mensajes + [{
            "role": "user",
            "content": "Haz un resumen breve (máximo 5 líneas) de lo que hemos platicado: "
                       "qué recetas o temas se trataron y qué recomendaciones te di al usuario."
        }]
        try:
            resumen = consultar_llm(peticion)
        except Exception as error:
            self.raiz.after(0, self._mostrar_error, str(error))
            return
        self.raiz.after(0, self._mostrar_respuesta, "Resumen de la conversación:\n" + resumen)

    def reiniciar(self):
        if not messagebox.askyesno("Nueva sesión", "¿Borrar el historial y comenzar de nuevo?"):
            return
        del mensajes[1:]            # Se conserva únicamente el mensaje de sistema
        bitacora.clear()
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.escribir("sistema", "Historial borrado. Nueva sesión iniciada.")


# ------------------------------------------------------------
# 7. PUNTO DE ENTRADA
# ------------------------------------------------------------
if __name__ == "__main__":
    ventana = tk.Tk()
    TutorGUI(ventana)
    ventana.mainloop()


#        SYSTEM  (Chef Sazón)
#          │
#          ▼
#     Comportamiento
#          │
#          ▼
# USER ──► LLM ──► ASSISTANT ──► Ventana tkinter
#          ▲                        │
#          └──── historial ◄────────┘  (botón "Resumen del historial")
