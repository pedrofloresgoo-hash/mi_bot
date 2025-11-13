import os
import sys
import streamlit as st
from openai import OpenAI
import re
import sqlite3 # <<< NUEVO: Para la base de datos
import datetime # <<< NUEVO: Para la hora del pedido
import json # <<< NUEVO: Para guardar el historial

# --- 1. CONFIGURACIÓN ---
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"

# --- <<< NUEVO: LÓGICA DE BASE DE DATOS (BD) >>> ---

def init_db(db_file="pedidos.db"):
    """Crea la base de datos y la tabla si no existen."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # Crear tabla
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ordenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        historial_chat TEXT NOT NULL,
        estado TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()

def registrar_pedido_en_db(historial_chat):
    """Guarda el historial de chat como un nuevo pedido en la BD."""
    try:
        conn = sqlite3.connect("pedidos.db")
        cursor = conn.cursor()
        
        # Convertir el historial (lista de dicts) a un string JSON
        historial_json = json.dumps(historial_chat, indent=2)
        
        # Insertar la orden
        cursor.execute("""
        INSERT INTO ordenes (timestamp, historial_chat, estado)
        VALUES (?, ?, ?)
        """, (str(datetime.datetime.now()), historial_json, "PENDIENTE"))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error al registrar el pedido en la BD: {e}")
        return False
# --- <<< FIN LÓGICA DE BD >>> ---


# --- <<< ACTUALIZADO: Cargar Menú (ahora crea un Diccionario) >>> ---
@st.cache_data
def cargar_menu(ruta_archivo="menu.txt"):
    """
    Lee el menú y crea un diccionario para mapear imágenes a nombres de platos.
    """
    try:
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            menu_texto_completo = f.read()
        
        menu_dict = {}
        # Expresión regular para encontrar: "Nombre del Plato: $Precio [ruta/imagen.png]"
        # O "Nombre del Plato: $Precio [sin_imagen]"
        pattern = re.compile(r"^(.*?):.*\$(\d+).*?\[(imagenes/.*?\.png)\].*$", re.MULTILINE)
        
        for match in pattern.finditer(menu_texto_completo):
            nombre_plato = match.group(1).strip()
            ruta_imagen = match.group(3).strip()
            if ruta_imagen != "sin_imagen":
                menu_dict[ruta_imagen] = nombre_plato
                
        return menu_texto_completo, menu_dict
    except FileNotFoundError:
        st.error(f"Error: No se encontró el archivo {ruta_archivo}. Asegúrate de que exista.")
        return None, None

# Cargar el menú y crear el prompt final
MENU_TEXTO, MENU_DICT = cargar_menu()

if MENU_TEXTO:
    DEFAULT_SYSTEM_PROMPT = """
Eres "ChatMesero", un asistente virtual para el restaurante "La Esquina".
Tu única misión es tomar la orden del cliente.

**REGLAS DE ORO (INQUEBRABLES):**
1.  **ROL ESTRICTO:** Solo eres un mesero. Si el cliente te pregunta por cualquier otra cosa (clima, deportes, etc.), debes responder: "Disculpe, solo puedo ayudarle a tomar su orden."
2.  **NO INVENTES:** Tu conocimiento se limita **ABSOLUTAMENTE** al menú de abajo.
3.  **REGLA DE FORMATO (¡LA MÁS IMPORTANTE!):**
    - Al mostrar el menú, DEBES copiar el texto, el precio y la etiqueta de imagen **EXACTAMENTE** como aparecen en el menú.
    - **EJEMPLO CORRECTO:** "Agua sin gas: $1 [imagenes/agua.png]"
4.  **REGLA DE GALERÍA HORIZONTAL:**
    - Cuando el usuario pida "Ver Menú Completo", tu respuesta DEBE empezar con **TODAS** las etiquetas de imagen de los platos principales juntas, en una sola línea.
    - **EJEMPLO:** "[imagenes/burger.png] [imagenes/pizza.png] [imagenes/ensalada.png] [imagenes/lomo.png]"

---
**MENÚ DISPONIBLE HOY (Productos a la Venta):**

{menu_inyectado}

---
Comienza la interacción.
""".format(menu_inyectado=MENU_TEXTO)
else:
    DEFAULT_SYSTEM_PROMPT = "Error: No se pudo cargar el menú."
# --- <<< FIN DE SECCIÓN ACTUALIZADA >>> ---


# --- 2. CLASE DEL CHATBOT (Sin cambios) ---
class DeepSeekChatbot:
    def __init__(self, api_key: str, model: str, system_prompt: str, base_url: str):
        try:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            self.model = model
            self.history = [{"role": "system", "content": system_prompt}]
        except Exception as e:
            st.error(f"Error fatal al inicializar el cliente: {e}")
            sys.exit(1)

    def send_message_stream(self, user_prompt: str):
        if not user_prompt:
            return
        self.history.append({"role": "user", "content": user_prompt})
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=self.history, temperature=0.7, stream=True
            )
            ai_response_chunks = []
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    ai_response_chunks.append(content)
                    yield content
            full_response = "".join(ai_response_chunks)
            self.history.append({"role": "assistant", "content": full_response})
        except Exception as e:
            yield f"\n[ERROR DE API] Ocurrió un error: {e}"
            self.history.pop()


# --- 3. LA APLICACIÓN WEB ---

def main_app():
    # Código para cargar CSS y layout="wide"
    st.set_page_config(page_title="ChatMesero", page_icon="🍔", layout="wide")

    # Cargar CSS personalizado (Asegúrate de que 'style.css' exista)
    try:
        st.markdown(
            f'<style>{open("style.css").read()}</style>',
            unsafe_allow_html=True
        )
    except FileNotFoundError:
        st.warning("No se encontró el archivo 'style.css'. Se usarán los estilos por defecto.")

    st.title("🍔 ChatBot del Restaurante")
    
    # <<< NUEVO: Inicializar la BD al arrancar >>>
    init_db()

    api_key = os.environ.get("DEEPSEEK_API_KEY") # O usa st.secrets si lo despliegas
    if not api_key:
        st.error("Error: Falta la API Key de DeepSeek.")
        st.stop()
        
    if not MENU_TEXTO or not MENU_DICT:
        st.error("Error fatal: No se pudo cargar el menú o el diccionario de imágenes.")
        st.stop()

    if "chatbot" not in st.session_state:
        st.session_state.chatbot = DeepSeekChatbot(
            api_key=api_key,
            model=DEFAULT_MODEL,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            base_url=DEEPSEEK_BASE_URL
        )
    
    # --- <<< NUEVO: BARRA LATERAL (SIDEBAR) CON ACCIONES >>> ---
    st.sidebar.title("Opciones de Pedido")

    if st.sidebar.button("Limpiar Chat 🧹"):
        st.session_state.chatbot = DeepSeekChatbot(
            api_key=api_key,
            model=DEFAULT_MODEL,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            base_url=DEEPSEEK_BASE_URL
        )
        st.success("Chat reiniciado.")
        st.rerun()

    if st.sidebar.button("Eliminar último mensaje ❌"):
        if len(st.session_state.chatbot.history) > 2: # No borrar el prompt del sistema
            st.session_state.chatbot.history.pop() # Borra respuesta de IA
            st.session_state.chatbot.history.pop() # Borra pregunta de Usuario
            st.success("Última interacción eliminada.")
            st.rerun()
        else:
            st.sidebar.warning("No hay nada que eliminar.")

    if st.sidebar.button("Confirmar y Enviar Pedido ✅"):
        # Extraer solo la conversación (sin el system prompt)
        orden_chat = [msg for msg in st.session_state.chatbot.history if msg["role"] != "system"]
        
        if len(orden_chat) == 0:
            st.sidebar.error("No hay ningún pedido que confirmar.")
        else:
            if registrar_pedido_en_db(orden_chat):
                st.sidebar.success("¡Pedido enviado a la cocina! 🧑‍🍳")
                st.balloons()
                # Opcional: limpiar el chat después de confirmar
                st.session_state.chatbot = DeepSeekChatbot(
                    api_key=api_key,
                    model=DEFAULT_MODEL,
                    system_prompt=DEFAULT_SYSTEM_PROMPT,
                    base_url=DEEPSEEK_BASE_URL
                )
                st.rerun()
            else:
                st.sidebar.error("Hubo un problema al enviar tu pedido.")
    # --- <<< FIN BARRA LATERAL >>> ---


    # --- <<< ACTUALIZADO: LÓGICA DE GALERÍA HORIZONTAL CON BOTONES >>> ---
    for message in st.session_state.chatbot.history:
        if message["role"] == "system": continue
        
        with st.chat_message(message["role"]):
            partes = re.split(r'(\[imagenes/.*?\])', message["content"])
            
            text_buffer = [] # Para acumular texto
            image_buffer = [] # Para acumular imágenes para la galería

            for parte in partes:
                if re.match(r'^\[imagenes/.*\]$', parte):
                    ruta_imagen = parte.strip("[]")
                    if os.path.exists(ruta_imagen):
                        image_buffer.append(ruta_imagen)
                    else:
                        text_buffer.append(f"(Error: No se encontró la imagen en {ruta_imagen})")
                elif parte == "[sin_imagen]":
                    pass
                else:
                    text_buffer.append(parte)
            
            # Mostrar todo el texto acumulado
            if text_buffer:
                st.markdown("".join(text_buffer).replace("\n", "  \n"))
            
            # Mostrar las imágenes en una galería horizontal (4 columnas)
            if image_buffer:
                # Usamos 4 columnas para un grid uniforme
                cols = st.columns(4)
                
                idx = 0
                for img_path in image_buffer:
                    with cols[idx]:
                        st.image(img_path, use_column_width=True) # <<< TAMAÑO UNIFORME
                        
                        # <<< NUEVO: LÓGICA DE BOTÓN CLICABLE >>>
                        item_name = MENU_DICT.get(img_path, "este item")
                        
                        # Usamos la ruta de la imagen como 'key' única para el botón
                        if st.button(f"Pedir {item_name}", key=f"btn_{img_path}_{message['content'][:10]}"):
                            st.session_state.prompt_a_enviar = f"Quiero pedir una {item_name}"
                            st.rerun() # Dispara el envío
                            
                    idx = (idx + 1) % 4 # Pasa a la siguiente columna (0, 1, 2, 3, 0, ...)

    # --- Opciones Predeterminadas (Botones) ---
    if "prompt_a_enviar" not in st.session_state:
        st.session_state.prompt_a_enviar = None

    # Mover los botones a la barra lateral para más limpieza
    st.sidebar.divider()
    st.sidebar.markdown("### Opciones Rápidas")
    if st.sidebar.button("Ver Menú Completo 📄"):
        st.session_state.prompt_a_enviar = "Muéstrame el menú completo"
        
    if st.sidebar.button("Ver Promociones 🔥"):
        st.session_state.prompt_a_enviar = "Qué promociones tienes hoy? (Asegúrate de mostrarme las fotos)"
        

    # --- Entrada de chat ---
    prompt_usuario = st.chat_input("Escribe tu pedido o pregunta...")
    
    if prompt_usuario:
        st.session_state.prompt_a_enviar = prompt_usuario

    # --- Lógica de envío ---
    if st.session_state.prompt_a_enviar:
        prompt_final = st.session_state.prompt_a_enviar
        st.session_state.prompt_a_enviar = None
        
        with st.chat_message("user"):
            st.markdown(prompt_final)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            respuesta_completa = ""
            for chunk in st.session_state.chatbot.send_message_stream(prompt_final):
                respuesta_completa += chunk
                placeholder.markdown(respuesta_completa + "▌")
            placeholder.empty()
        
        st.rerun()

if __name__ == "__main__":
    main_app()