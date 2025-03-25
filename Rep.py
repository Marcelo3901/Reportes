import gspread
import pandas as pd

# Conexión a Google Sheets (sin credenciales)
gc = gspread.service_account(filename=None)  # Usar None para conexión sin credenciales

# URL de tu hoja de Google Sheets (puedes usar la URL pública)
url = 'https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/edit?usp=sharing'

# Abre la hoja de cálculo usando la URL
sheet = gc.open_by_url(url)

# Selecciona la hoja que deseas leer
worksheet = sheet.get_worksheet(0)  # Puedes cambiar el índice si tienes varias hojas

# Lee todos los registros de la hoja y conviértelos en un DataFrame de pandas
data = worksheet.get_all_records()  # Esto lee todos los registros
df = pd.DataFrame(data)

# Muestra los primeros registros para verificar
print(df.head())
