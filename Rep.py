import pandas as pd
import streamlit as st

# Función para obtener los datos desde la hoja pública de Google Sheets en formato CSV
def obtener_datos_de_hoja(sheet_url, sheet_name):
    try:
        # Construir la URL para obtener el CSV (asegúrate de que la hoja esté publicada)
        url = f"{sheet_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        st.write("URL utilizada para obtener los datos:", url)
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()  # Limpiar espacios en los nombres de las columnas
        
        st.write("Columnas detectadas:", list(df.columns))
        st.write("Vista previa de las primeras filas:")
        st.write(df.head(10))
        
        # Verificar que existan las columnas requeridas
        required = ["Código", "Estado", "Estilo", "Marca temporal"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            st.error(f"Faltan columnas requeridas: {missing}")
            return pd.DataFrame()
        
        # Eliminar filas donde "Código" sea nulo o vacío
        df = df[df["Código"].notna()]
        df = df[df["Código"].astype(str).str.strip() != ""]
        
        return df
    except Exception as e:
        st.error(f"Error al obtener datos: {e}")
        return pd.DataFrame()

# Parámetros: URL base de la hoja y nombre de la hoja (debe coincidir exactamente)
sheet_url = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY"
sheet_name = "DatosM"  # Revisa que el nombre sea exactamente igual al de la pestaña en el Sheet

# Obtener datos
df = obtener_datos_de_hoja(sheet_url, sheet_name)

if not df.empty:
    # Convertir "Marca temporal" a datetime
    try:
        df['Marca temporal'] = pd.to_datetime(df['Marca temporal'], format='%d/%m/%Y %H:%M:%S')
    except Exception as e:
        st.error(f"Error al convertir 'Marca temporal': {e}")
    
    # Ordenar por "Marca temporal" descendente y conservar solo el registro más reciente por "Código"
    df = df.sort_values('Marca temporal', ascending=False)
    df = df.drop_duplicates(subset='Código', keep='first')
    
    # Normalizar las columnas "Estado" y "Estilo"
    df["Estado_norm"] = df["Estado"].astype(str).str.strip().str.lower()
    df["Estilo_norm"] = df["Estilo"].astype(str).str.strip()
    
    # Filtrar solo los registros cuyo estado sea "en cuarto frio"
    df_cf = df[df["Estado_norm"] == "en cuarto frio"]
    
    # Función para determinar la capacidad según los dos primeros dígitos del código
    def obtener_capacidad(codigo):
        codigo_str = str(codigo).strip()
        if codigo_str.startswith("20"):
            return 20
        elif codigo_str.startswith("30"):
            return 30
        elif codigo_str.startswith("58"):
            return 58
        else:
            return 0  # Si no es un código reconocido
    
    # Aplicar la función para calcular los litros (capacidad) por barril
    df_cf["Litros"] = df_cf["Código"].apply(obtener_capacidad)
    
    # Calcular totales
    total_barriles = df_cf.shape[0]
    litros_totales = df_cf["Litros"].sum()
    litros_por_estilo = df_cf.groupby("Estilo_norm")["Litros"].sum()
    
    # Mostrar el reporte en Streamlit
    st.title("Reporte de Inventario de Barriles en Cuarto Frío")
    st.subheader("Resumen del Inventario")
    st.write(f"**Barriles Totales:** {total_barriles}")
    st.write(f"**Litros Totales:** {litros_totales} litros")
    
    st.subheader("Litros por Estilo")
    st.write(litros_por_estilo)
    
    st.subheader("Detalle del Inventario")
    st.write(df_cf[["Marca temporal", "Código", "Estilo_norm", "Estado", "Litros"]])
else:
    st.error("No se cargaron datos.")
