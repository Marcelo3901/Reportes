import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# Definir el alcance de las credenciales de la API
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Autenticación usando el archivo credentials.json
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

# Abre la hoja de cálculo utilizando el URL de tu hoja de Google Sheets
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/edit?usp=sharing")

# Selecciona la hoja que quieres acceder, por ejemplo la primera hoja
worksheet = sheet.get_worksheet(0)

# Lee todos los registros de la hoja y conviértelos en un DataFrame de pandas
data = worksheet.get_all_records()  # Esto lee todos los registros
df = pd.DataFrame(data)

# Muestra los datos en Streamlit
st.write(df)

# Puedes agregar más lógica aquí para generar los reportes o métricas que necesitas
