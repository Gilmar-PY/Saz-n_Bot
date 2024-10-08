import pandas as pd
import streamlit as st
from datetime import datetime
from copy import deepcopy
import openai
import csv
import re
import pytz
import json
import logging

# Configura el logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Inicializar el cliente de OpenAI con la clave API
openai.api_key = st.secrets["OPENAI"]["API_KEY"]

# Configuración inicial de la página
st.set_page_config(page_title="SazónBot", page_icon=":pot_of_food:")
st.title("🍲 SazónBot")

# Mensaje de bienvenida
intro = """¡Bienvenido a Sazón Bot, el lugar donde todos tus antojos de almuerzo se hacen realidad!
Comienza a chatear con Sazón Bot y descubre qué puedes pedir, cuánto cuesta y cómo realizar tu pago. ¡Estamos aquí para ayudarte a disfrutar del mejor almuerzo!"""
st.markdown(intro)


# Cargar el menú desde un archivo CSV
def load(file_path):
    """Cargar el menú desde un archivo CSV con columnas Plato, Descripción y Precio."""
    return pd.read_csv(file_path)

# Mostrar el menú con descripciones
def format_menu(menu):
    if menu.empty:
        return "No hay platos disponibles."
    else:
        # Encabezados de la tabla
        table = "| **Plato** | **Descripción** | **Precio** |\n"
        table += "|-----------|-----------------|-------------|\n"  # Línea de separación
        
        # Filas de la tabla
        for idx, row in menu.iterrows():
            table += f"| {row['Plato']} | {row['Descripción']} | S/{row['Precio']:.2f} |\n"
        
        return table


# Mostrar el menú con descripciones
def display_menu(menu):
    """Mostrar el menú con descripciones."""
    menu_text = "Aquí está nuestra carta:\n"
    for index, row in menu.iterrows():
        menu_text += f"{row['Plato']}: {row['Descripción']} - {row['Precio']} soles\n"
    return menu_text

# Mostrar los distritos de reparto
def display_distritos(distritos):
    """Mostrar los distritos de reparto disponibles."""
    distritos_text = "Los distritos de reparto son:\n"
    for index, row in distritos.iterrows():
        distritos_text += f"**{row['Distrito']}**\n"
    return distritos_text

# Cargar el menú y distritos
menu = load("carta.csv")
distritos = load("distritos.csv")
bebidas= load("Bebidas.csv")
postres= load("Postres.csv")

# Generar tabla de pedido confirmado
def display_confirmed_order(order_details):
    """Genera una tabla en formato Markdown para el pedido confirmado."""
    table = "| **Plato** | **Cantidad** | **Precio Total** |\n"
    table += "|-----------|--------------|------------------|\n"
    for item in order_details:
        table += f"| {item['Plato']} | {item['Cantidad']} | S/{item['Precio Total']:.2f} |\n"
    table += "| **Total** |              | **S/ {:.2f}**      |\n".format(sum(item['Precio Total'] for item in order_details))
    return table

def get_system_prompt(menu, distritos):
    """Define el prompt del sistema para el bot de Sazón incluyendo el menú y distritos."""
    lima_tz = pytz.timezone('America/Lima')  # Define la zona horaria de Lima
    hora_lima = datetime.now(lima_tz).strftime("%Y-%m-%d %H:%M:%S")  # Obtiene la hora actual en Lima
    system_prompt = f"""
    Eres el bot de pedidos de Sazón, amable y servicial. Ayudas a los clientes a hacer sus pedidos y siempre confirmas que solo pidan platos que están en el menú oficial. Aquí tienes el menú para mostrárselo a los clientes:\n{display_menu(menu)}\n
    También repartimos en los siguientes distritos: {display_distritos(distritos)}.\n
    Primero, saluda al cliente y ofrécele el menú. Asegúrate de que el cliente solo seleccione platos que están en el menú actual y explícales que no podemos preparar platos fuera del menú.
    El cliente puede indicar la cantidad en texto o en números.
    **IMPORTANTE: Validación de cantidad solicitada**
    - Si la cantidad solicitada está en el rango de 1 a 100 (inclusive), acepta el pedido sin mostrar advertencias.
    - Si la cantidad solicitada es mayor que 100, muestra el siguiente mensaje:
      "Lamento informarte que el límite máximo de cantidad por producto es de 100 unidades. Por favor, reduce la cantidad para procesar tu pedido."
    
    Pregunta si desea recoger su pedido en el local o si prefiere entrega a domicilio. 
    Si elige entrega, pregúntale al cliente a qué distrito desea que se le envíe su pedido, confirma que el distrito esté dentro de las zonas de reparto y verifica el distrito de entrega con el cliente.
    Si el pedido es para recoger, invítalo a acercarse a nuestro local ubicado en UPCH123.
    
    Usa solo español peruano en tus respuestas.
    
    Antes de continuar, confirma que el cliente haya ingresado un método de entrega válido. Luego, resume el pedido en la siguiente tabla:\n
    | **Plato**      | **Cantidad** | **Precio Total** |\n
    |----------------|--------------|------------------|\n
    |                |              |                  |\n
    | **Total**      |              | **S/ 0.00**      |\n
    
    Pregunta al cliente si quiere añadir una bebida o postre. 
    - Si responde bebida, muéstrale únicamente la carta de bebidas {display_menu(bebidas)}.
    - Si responde postre, muéstrale solo la carta de postres {display_menu(postres)}.
    
    Si el cliente agrega postres o bebidas, incorpóralos en la tabla de resumen como un plato adicional y calcula el monto total nuevamente.
    
    Pregunta al cliente: "¿Estás de acuerdo con el pedido?" y espera su confirmación. 
    
    Luego, si confirma, pide el método de pago (tarjeta de crédito, efectivo u otra opción disponible). Verifica que haya ingresado un método de pago antes de continuar.
    
    Una vez que el cliente confirme el método de pago, registra la hora actual de Perú como el timestamp {hora_lima} de la confirmación. 
    El pedido confirmado será:\n
    {display_confirmed_order([{'Plato': '', 'Cantidad': 0, 'Precio Total': 0}])}\n
    
    Recuerda siempre confirmar que el pedido y el método de pago estén completos antes de registrarlo.
    """
    return system_prompt.replace("\n", " ")

def generate_response(prompt, temperature=0.5, max_tokens=1000):
    """Enviar el prompt a OpenAI y devolver la respuesta."""
    st.session_state["messages"].append({"role": "user", "content": prompt})

    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=st.session_state["messages"],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    response = completion.choices[0].message['content']
    st.session_state["messages"].append({"role": "assistant", "content": response})

    return response

# Estado inicial
initial_state = [
    {"role": "system", "content": get_system_prompt(menu, distritos)},
    {
        "role": "assistant",
        "content": f"¿Qué te puedo ofrecer?\n\nEste es el menú del día:\n\n{format_menu(menu)}",
    },
]

# Inicializar el historial de mensajes
if "messages" not in st.session_state:
    st.session_state["messages"] = deepcopy(initial_state)

# Botón para eliminar la conversación
clear_button = st.button("Eliminar conversación", key="clear")
if clear_button:
    st.session_state["messages"] = deepcopy(initial_state)

# Mostrar el historial de mensajes
for message in st.session_state.messages:
    if message["role"] == "assistant":
        with st.chat_message("assistant", avatar="👨‍🍳"):
            st.markdown(message["content"])
    else:
        with st.chat_message("user", avatar="👤"):
            st.markdown(message["content"])

# Input del usuario
if prompt := st.chat_input():
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    output = generate_response(prompt)
    with st.chat_message("assistant", avatar="👨‍🍳"):
        st.markdown(output)
