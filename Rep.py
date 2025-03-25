import streamlit as st
import gspread
import pandas as pd

# Conexión a Google Sheets (sin credenciales)
gc = gspread.service_account(filename=None)  # Usar None para conexión sin credenciales

# URL de tu hoja de Google Sheets
url = 'https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/edit?usp=sharing'

# Abre la hoja de cálculo usando la URL
sheet = gc.open_by_url(url)

# Selecciona la hoja que deseas leer
worksheet = sheet.get_worksheet(2)

# Lee todos los registros de la hoja y conviértelos en un DataFrame de pandas
data = worksheet.get_all_records()
df = pd.DataFrame(data)

# Muestra el DataFrame en Streamlit
st.title('Reporte de Inventario')
st.write(df)

# Aquí puedes agregar más lógica para procesar o filtrar la información
