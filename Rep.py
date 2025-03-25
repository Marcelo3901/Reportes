import gspread
import pandas as pd

# Conectar con la hoja de Google Sheets pública sin credenciales
gc = gspread.Client(None)

# URL de la hoja de Google Sheets pública
url = 'https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/edit?usp=sharing'

# Abre la hoja de cálculo usando la URL
sheet = gc.open_by_url(url)

# Selecciona la hoja que deseas leer
worksheet = sheet.get_worksheet(0)  # Primer hoja

# Lee todos los registros de la hoja y conviértelos en un DataFrame de pandas
data = worksheet.get_all_records()
df = pd.DataFrame(data)

# Muestra el DataFrame en Streamlit
import streamlit as st
st.title('Reporte de Inventario')
st.write(df)
