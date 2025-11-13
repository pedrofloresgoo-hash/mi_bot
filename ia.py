import os
import sys
import streamlit as st
from openai import OpenAI
import re  # <<< --- ¡NUEVO! Importar expresiones regulares

# --- 1. CONFIGURACIÓN ---
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"

# --- Función para cargar el menú ---
@st.cache_data
def cargar_menu(ruta_archivo="menu.txt"):
    try:
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Error: No se encontró el archivo {ruta_archivo}. Asegúrate de que exista.")
        return None

# Cargar el menú y crear el prompt final
MENU_TEXTO = cargar_menu()
if MENU_TEXTO:
    DEFAULT_SYSTEM_PROMPT = """
Eres "ChatMesero", un asistente virtual para tomar pedidos en el restaurante "La Esquina".
Tu única misión es tomar la orden del cliente.

**REGLAS ESTRICTAS:**
1.  **Rol Único:** Solo eres un mesero. No puedes hablar de nada que no sea la comida y bebida del restaurante.
2.  **Rechazo Amable:** Si el cliente te saca de tema, debes responder: "Disculpe, solo puedo ayudarle a tomar su orden. ¿Qué le gustaría pedir del menú?"
3.  **Proactivo:** Sugiere el "Plato del Día" o la "Promo Burger".
4.  **Basado en el Menú:** Solo puedes vender lo que está en la lista de abajo.

5.  **<<< ¡NUEVA REGLA DE IMÁGENES! >>>**
    Cuando describas un plato que tiene una imagen en el menú (ej. [imagenes/burger.png]), **DEBES** incluir esa etiqueta de imagen exacta en tu respuesta. El sistema la mostrará automáticamente. No incluyas la etiqueta [sin_imagen].

---
**MENÚ DISPONIBLE HOY (Productos a la Venta):**

{menu_inyectado}

---
Comienza la interacción.
""".format(menu_inyectado=MENU_TEXTO)
else:
    DEFAULT_SYSTEM_PROMPT = "Error: No se pudo cargar el menú."


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
    st.set_page_config(page_title="ChatMesero", page_icon="🍔")
    st.title("🍔 ChatBot del Restaurante")

    api_key = os.environ.get("DEEPSEEK_API_KEY") # O usa st.secrets si lo despliegas
    if not api_key:
        st.error("Error: Falta la API Key de DeepSeek.")
        st.stop()
        
    if not MENU_TEXTO:
        st.stop()

    if "chatbot" not in st.session_state:
        st.session_state.chatbot = DeepSeekChatbot(
            api_key=api_key,
            model=DEFAULT_MODEL,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            base_url=DEEPSEEK_BASE_URL
        )

    # --- <<< ¡CAMBIO IMPORTANTE! LÓGICA PARA MOSTRAR HISTORIAL CON IMÁGENES >>> ---
    for message in st.session_state.chatbot.history:
        if message["role"] == "system": continue
        
        with st.chat_message(message["role"]):
            # Divide el mensaje por las etiquetas de imagen (ej. [imagenes/burger.png])
            partes = re.split(r'(\[imagenes/.*?\])', message["content"])
            
            for parte in partes:
                # Si la parte es una etiqueta de imagen válida...
                if re.match(r'^\[imagenes/.*\]$', parte):
                    ruta_imagen = parte.strip("[]") # Quita los corchetes
                    
                    # Verifica si el archivo de imagen existe antes de mostrarlo
                    if os.path.exists(ruta_imagen):
                        st.image(ruta_imagen, width=300)
                    else:
                        st.error(f"(Error: No se encontró la imagen en {ruta_imagen})")
                elif parte == "[sin_imagen]":
                    pass # Ignora esta etiqueta
                else:
                    # Muestra el texto normal
                    st.markdown(parte.replace("\n", "  \n"))
    # --- <<< FIN DEL CAMBIO >>> ---


    # --- Opciones Predeterminadas (Botones) ---
    if "prompt_a_enviar" not in st.session_state:
        st.session_state.prompt_a_enviar = None

    col1, col2, col3 = st.columns(3)
    if col1.button("Ver Menú Completo 📄"):
        st.session_state.prompt_a_enviar = "Muéstrame el menú completo"
        
    if col2.button("Ver Promociones 🔥"):
        st.session_state.prompt_a_enviar = "Qué promociones tienes hoy? (Asegúrate de mostrarme las fotos)"
        
    if col3.button("Limpiar Chat 🧹"):
        st.session_state.chatbot = DeepSeekChatbot(
            api_key=api_key,
            model=DEFAULT_MODEL,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            base_url=DEEPSEEK_BASE_URL
        )
        st.rerun()

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
            # Usamos st.empty() para un efecto visual más limpio
            placeholder = st.empty()
            respuesta_completa = ""
            for chunk in st.session_state.chatbot.send_message_stream(prompt_final):
                respuesta_completa += chunk
                placeholder.markdown(respuesta_completa + "▌") # Muestra el cursor
            placeholder.empty() # Limpia el placeholder
        
        # Refresca la app para que la lógica de renderizado de imágenes se ejecute
        st.rerun()

if __name__ == "__main__":
    main_app()
