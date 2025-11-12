import os
import sys
import streamlit as st
from openai import OpenAI

# --- 1. CONFIGURACIÓN ---
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"

# --- ¡AQUÍ SE CONTROLA EL IDIOMA! ---
# Esta es la instrucción que le dice a la IA cómo actuar y en qué idioma.
DEFAULT_SYSTEM_PROMPT = (
    "Eres una persona que murio y hoy te dedicas a ayudar a las personas , "
    "optimizado para dar respuestas claras y concisas en español."
)
# Si quieres el "modo experto", reemplaza el texto de arriba con el prompt experto.


# --- 2. CLASE DEL CHATBOT (Sin cambios) ---
class DeepSeekChatbot:
    def __init__(self, api_key: str, model: str, system_prompt: str, base_url: str):
        try:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            self.model = model
            self.history = [{"role": "system", "content": system_prompt}]
        except Exception as e:
            print(f"Error fatal al inicializar el cliente de OpenAI: {e}", file=sys.stderr)
            sys.exit(1)

    def send_message_stream(self, user_prompt: str):
        if not user_prompt:
            return

        self.history.append({"role": "user", "content": user_prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.history,
                temperature=0.7,
                stream=True
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

# --- 3. LA APLICACIÓN WEB CON STREAMLIT ---

def main_app():
    # --- Configuración de la página ---
    st.set_page_config(page_title="DeepSeek Chat", page_icon="🤖")
    st.title("🤖 Chatbot con Pedro")

    # --- Cargar la API Key (¡Seguro!) ---
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        st.error("Error: La variable de entorno DEEPSEEK_API_KEY no está configurada.")
        st.info("Ejecuta 'export DEEPSEEK_API_KEY=...' en tu terminal y reinicia Streamlit.")
        st.stop()

    # --- NUEVO: Barra Lateral (Sidebar) ---
    st.sidebar.title("Opciones")
    st.sidebar.caption("Aquí puedes gestionar el chat.")

    if st.sidebar.button("🧹 Limpiar Chat"):
        # Al presionar el botón, reiniciamos el bot y refrescamos la página
        st.session_state.chatbot = DeepSeekChatbot(
            api_key=api_key,
            model=DEFAULT_MODEL,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            base_url=DEEPSEEK_BASE_URL
        )
        st.rerun() # Refresca la UI

    # --- Inicializar el Bot (Usando el estado de la sesión) ---
    if "chatbot" not in st.session_state:
        st.session_state.chatbot = DeepSeekChatbot(
            api_key=api_key,
            model=DEFAULT_MODEL,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            base_url=DEEPSEEK_BASE_URL
        )

    # --- Mostrar el historial de chat ---
    for message in st.session_state.chatbot.history:
        if message["role"] == "system":
            continue
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # --- Cuadro de entrada del usuario (al final de la página) ---
    if prompt := st.chat_input("Escribe tu mensaje aquí..."):
        
        # Mostrar mensaje de usuario
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generar y mostrar respuesta de la IA
        with st.chat_message("assistant"):
            response_stream = st.session_state.chatbot.send_message_stream(prompt)
            st.write_stream(response_stream)

if __name__ == "__main__":
    main_app()