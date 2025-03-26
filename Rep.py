import pandas as pd
import streamlit as st

# Función para obtener los datos desde la hoja de Google Sheets pública en formato CSV
def obtener_datos_de_hoja(sheet_url, sheet_name):
    try:
        # Construir la URL usando el formato CSV de Google Sheets
        url = f"{sheet_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()  # Limpiar los nombres de las columnas
        
        # Verificar que la columna 'Código' exista
        if "Código" not in df.columns:
            raise ValueError(f"La columna 'Código' no se encontró en las columnas: {list(df.columns)}")
        
        # Eliminar filas donde la columna 'Código' esté vacía o nula
        df.dropna(subset=["Código"], inplace=True)
        df = df[df["Código"].astype(str).str.strip() != ""]
        
        return df
    except Exception as e:
        st.warning(f"⚠️ No se pudieron cargar los datos: {e}")
        return pd.DataFrame()

# URL base de la hoja de Google Sheets (sin la parte final "/edit?...")
sheet_url = 'https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/edit?gid=1454588454#gid=1454588454'
sheet_name = 'DatosM'  # Nombre de la hoja que contiene los datos de movimientos de barriles

# Obtener los datos de la hoja
df = obtener_datos_de_hoja(sheet_url, sheet_name)

if not df.empty:
    # Convertir la columna "Marca temporal" a datetime
    try:
        df['Marca temporal'] = pd.to_datetime(df['Marca temporal'], format='%d/%m/%Y %H:%M:%S')
    except Exception as e:
        st.warning(f"⚠️ Error al convertir la columna 'Marca temporal': {e}")
    
    # Ordenar por marca temporal descendente y mantener el registro más reciente por 'Código'
    df = df.sort_values('Marca temporal', ascending=False)
    df = df.drop_duplicates(subset='Código', keep='first')
    
    # Normalizar las columnas 'Estado' y 'Estilo'
    df['Estado_normalizado'] = df['Estado'].astype(str).str.strip().str.lower()
    df['Estilo_normalizado'] = df['Estilo'].astype(str).str.strip()
    
    # Filtrar solo aquellos registros cuyo Estado sea "en cuarto frio"
    df = df[df['Estado_normalizado'] == 'en cuarto frio']
    
    # Función para determinar la capacidad del barril según los dos primeros dígitos del código
    def obtener_capacidad(codigo):
        codigo_str = str(codigo).strip()
        if codigo_str.startswith('20'):
            return 20
        elif codigo_str.startswith('30'):
            return 30
        elif codigo_str.startswith('58'):
            return 58
        else:
            return 0  # Si no es un código conocido, asignar 0
    
    df['Capacidad'] = df['Código'].apply(obtener_capacidad)
    
    # Calcular los litros totales
    litros_totales = df['Capacidad'].sum()
    # Calcular los litros por estilo utilizando la columna normalizada
    litros_por_estilo = df.groupby('Estilo_normalizado')['Capacidad'].sum()
    
    # Mostrar resultados en Streamlit
    st.title('Reporte de Inventario de Barriles')
    
    st.subheader('Totales de Inventario (Cuarto Frío)')
    st.write(f"**Barriles Totales:** {df.shape[0]}")
    st.write(f"**Litros Totales:** {litros_totales} litros")
    
    st.subheader('Litros por Estilo')
    st.write(litros_por_estilo)
    
    st.subheader('Detalle del Inventario')
    st.write(df[['Marca temporal', 'Código', 'Estilo_normalizado', 'Estado', 'Capacidad']])
    
    # Salida de verificación: mostrar las primeras filas para revisar datos
    st.subheader('Vista previa de datos')
    st.write(df.head())
else:
    st.warning("⚠️ No se encontraron datos para mostrar.")
