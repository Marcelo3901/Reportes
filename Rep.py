import pandas as pd
import streamlit as st
import requests

# URL de la hoja de Google Sheets (con el ID de la hoja)
sheet_id = '1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY'
range_name = 'DatosM'  # Nombre de la hoja o el rango de celdas que quieras obtener

# Construir la URL de la API de Google Sheets para acceder a los datos
url = f'https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{range_name}?key=YOUR_PUBLIC_API_KEY'

# Realizar la solicitud a la API de Google Sheets
response = requests.get(url)
data = response.json()

# Si la respuesta contiene datos, procesarlos
if 'values' in data:
    # Convertir los datos de Google Sheets a un DataFrame de pandas
    df = pd.DataFrame(data['values'][1:], columns=data['values'][0])  # Usar la primera fila como columnas
    
    # Mostrar el DataFrame en Streamlit
    st.title('Reporte de Inventario')
    st.write(df)
else:
    st.error("No se pudieron obtener los datos de la hoja de cálculo.")
