import os
import sys
import streamlit as st
from openai import OpenAI
import re  # Importar expresiones regulares

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

# --- <<< CORREGIDO >>> ---
# Cargar el menú y crear el prompt final (una sola vez)
MENU_TEXTO = cargar_menu()
if MENU_TEXTO:
    DEFAULT_SYSTEM_PROMPT = """
Eres "ChatMesero", un asistente virtual para el restaurante "La Esquina".
Tu única misión es tomar la orden del cliente.

**REGLAS DE ORO (INQUEBRABLES):**

1.  **ROL ESTRICTO:** Solo eres un mesero. Si el cliente te pregunta por cualquier otra cosa (clima, deportes, etc.), debes responder: "Disculpe, solo puedo ayudarle a tomar su orden."
2.  **NO INVENTES:** No puedes alucinar. Tu conocimiento se limita **ABSOLUTAMENTE** al menú de abajo.
3.  **REGLA DE FORMATO (¡LA MÁS IMPORTANTE!):**
    - Al mostrar el menú, DEBES copiar el texto, el precio y la etiqueta de imagen **EXACTAMENTE** como aparecen en el menú.
    - **EJEMPLO CORRECTO:** "Agua sin gas: $1 [imagenes/agua.png]"
    - **EJEMPLO INCORRECTO (PROHIBIDO):** "2.Aguasingas -1"
    - **NUNCA** alteres el precio. **NUNCA** alteres el nombre del plato.

4.  **REGLA DE GALERÍA HORIZONTAL:**
    - Cuando el usuario pida "Ver Menú Completo" o "Ver Promociones", tu respuesta DEBE empezar con **TODAS** las etiquetas de imagen relevantes juntas, en una sola línea.
    - **EJEMPLO DE RESPUESTA DE GALERÍA:**
      "¡Claro! Aquí están nuestros platos principales:
      [imagenes/burger.png] [imagenes/pizza.png] [imagenes/ensalada.png] [imagenes/lomo.png]

      === PLATOS FUERTES ===
      Promo Burger (Hamburguesa + Papas + Gaseosa): $10 [imagenes/burger.png]
      Pizza Margarita: $12 [imagenes/pizza.png]
      ..."
    - Esta regla es vital para que el código de la galería funcione.

---
**MENÚ DISPONIBLE HOY (Productos a la Venta):**

{menu_inyectado}

---
Comienza la interacción.
""".format(menu_inyectado=MENU_TEXTO)
else:
    DEFAULT_SYSTEM_PROMPT = "Error: No se pudo cargar el menú."
# --- <<< FIN DE SECCIÓN CORREGIDA >>> ---


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

# --- <<< CORREGIDO >>> ---
# Solo hay UNA definición de main_app()
def main_app():
    # Código para cargar CSS y layout="wide" movido aquí
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

    # --- <<< CORREGIDO: LÓGICA DE GALERÍA HORIZONTAL >>> ---
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
            
            # Mostrar las imágenes en una galería horizontal
            if image_buffer:
                num_imagenes = len(image_buffer)
                # Crea columnas, una por cada imagen (limitado para no saturar)
                cols = st.columns(num_imagenes if num_imagenes < 6 else 6) 
                
                idx = 0
                for img_path in image_buffer:
                    with cols[idx]:
                        st.image(img_path, use_column_width=True, caption=img_path.split('/')[-1].split('.')[0].capitalize())
                    idx = (idx + 1) % len(cols)

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
            placeholder = st.empty()
            respuesta_completa = ""
            for chunk in st.session_state.chatbot.send_message_stream(prompt_final):
                respuesta_completa += chunk
                placeholder.markdown(respuesta_completa + "▌")
            placeholder.empty()
        
        st.rerun()

# --- <<< CORREGIDO >>> ---
# Solo hay UN bloque "if __name__ == '__main__':" al final
if __name__ == "__main__":
    main_app()