import gspread
import pandas as pd
import streamlit as st

# Función para obtener datos de una hoja pública de Google Sheets
def obtener_datos_de_hoja(sheet_url):
    # Conectar con la hoja pública de Google Sheets
    gc = gspread.service_account(filename=None)  # No necesitamos credenciales
    sheet = gc.open_by_url(sheet_url)
    worksheet = sheet.sheet1  # Accede a la primera hoja del archivo
    
    # Obtener todos los registros de la hoja
    data = worksheet.get_all_records()
    
    # Convertir los registros a un DataFrame de pandas
    df = pd.DataFrame(data)
    
    return df

# URL de la hoja de Google Sheets (pública)
sheet_url = 'https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/edit?usp=sharing'

# Llamar la función para obtener los datos
df = obtener_datos_de_hoja(sheet_url)

# Preprocesar los datos para el reporte de inventario
df['Marca temporal'] = pd.to_datetime(df['Marca temporal'], format='%d/%m/%Y %H:%M:%S')
df = df.sort_values('Marca temporal', ascending=False)  # Ordenar los registros por la marca temporal
df = df.drop_duplicates(subset='Código', keep='first')  # Eliminar registros duplicados, manteniendo solo el más reciente

# Determinar la capacidad de los barriles según los dos primeros dígitos del código
def obtener_capacidad(codigo):
    if str(codigo).startswith('20'):
        return 20
    elif str(codigo).startswith('30'):
        return 30
    elif str(codigo).startswith('58'):
        return 58
    else:
        return 0  # Si no es un código conocido, asignamos 0 como capacidad desconocida

df['Capacidad'] = df['Código'].apply(obtener_capacidad)

# Calcular los litros totales y los litros por estilo
litros_totales = df['Capacidad'].sum()
litros_por_estilo = df.groupby('Estilo')['Capacidad'].sum()

# Mostrar los resultados en Streamlit
st.title('Reporte de Inventario de Barriles')

# Reporte general
st.subheader(f'Totales de Inventario (Cuarto Frío)')
st.write(f'**Barriles Totales:** {df.shape[0]}')
st.write(f'**Litros Totales:** {litros_totales} litros')

# Reporte por estilo
st.subheader('Litros por Estilo')
st.write(litros_por_estilo)

# Mostrar los datos en una tabla
st.subheader('Detalle del Inventario')
st.write(df[['Marca temporal', 'Código', 'Estilo', 'Estado', 'Capacidad']])
