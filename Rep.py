import pandas as pd
import streamlit as st

def obtener_datos_de_hoja(sheet_url, sheet_name):
    try:
        # Construir la URL para obtener el CSV de la hoja especificada
        url = f"{sheet_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        st.write("URL utilizada para obtener los datos:", url)
        
        # Leer los datos desde la URL
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()  # Limpiar espacios en los nombres de las columnas
        
        # Mostrar información de depuración
        st.write("Columnas detectadas:", list(df.columns))
        st.write("Vista previa de las primeras filas:")
        st.write(df.head())
        
        return df
    except Exception as e:
        st.error(f"Error al obtener datos: {e}")
        return pd.DataFrame()

# URL base de la hoja de Google Sheets (sin la parte final "/edit?...")
sheet_url = 'https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY'
# Nombre de la hoja que queremos leer. Asegúrate de que coincide exactamente con el nombre (por ejemplo, "DatosM")
sheet_name = 'DatosM'

# Obtener los datos de la hoja
df = obtener_datos_de_hoja(sheet_url, sheet_name)

# Mostrar el tamaño del DataFrame
st.write("Dimensiones del DataFrame:", df.shape)

# Verificar si la columna "Código" existe
if "Código" in df.columns:
    st.success("La columna 'Código' fue encontrada.")
else:
    st.error("La columna 'Código' no se encontró. Verifica el nombre de la hoja y las columnas en el CSV.")

# Mostrar la vista previa del DataFrame
st.write("Vista completa de datos (primeras 10 filas):")
st.write(df.head(10))
