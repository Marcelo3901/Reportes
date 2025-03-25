import streamlit as st
import pandas as pd
import plotly.express as px
import urllib.parse

# URL base de la hoja de cálculo en Google Sheets (debe ser un enlace público CSV)
BASE_URL = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/gviz/tq?tqx=out:csv&sheet="

# Nombres de hojas corregidos
SHEETS = {
    "InventarioLatas": "InventarioLatas",
    "DatosM": "DatosM",
    "VLatas": "VLatas",
    "RClientes": "RClientes"
}

# Cargar datos de cada hoja
def cargar_datos(hoja_nombre):
    try:
        url = BASE_URL + urllib.parse.quote(SHEETS[hoja_nombre])
        df = pd.read_csv(url, dtype=str)
        df = df.dropna(how='all')  # Eliminar filas completamente vacías
        df.columns = df.columns.str.strip()  # Limpiar nombres de columnas
        df = df.loc[:, ~df.columns.duplicated()]  # Eliminar columnas duplicadas
        
        if df.empty or df.shape[1] < 2 or all(df.columns.str.contains("Unnamed")):
            st.warning(f"No se encontraron datos en la hoja {hoja_nombre} o la hoja está vacía.")
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"Error al cargar datos de {hoja_nombre}: {e}")
        return pd.DataFrame()

# Cargar cada hoja de la base de datos
df_latas = cargar_datos("InventarioLatas")
df_barriles = cargar_datos("DatosM")
df_ventas_latas = cargar_datos("VLatas")
df_clientes = cargar_datos("RClientes")

# Reporte de barriles
def reporte_barriles(df):
    st.subheader("Estado de los Barriles y Litros Totales")
    
    # Renombrar columnas si es necesario
    columnas_mapeo = {
        "Código": "Codigo",
        "Estilo.1": "Estilo",
        "Cliente.1": "Cliente",
        "Estado.1": "Estado",
        "Responsable.1": "Responsable",
        "Observaciones.2": "Observaciones"
    }
    df = df.rename(columns=columnas_mapeo)
    
    columnas_necesarias = {'Codigo', 'Estilo', 'Cliente', 'Estado', 'Responsable', 'Observaciones'}
    
    if not columnas_necesarias.issubset(df.columns):
        st.warning("No hay datos de barriles disponibles o faltan columnas necesarias.")
        st.write("Columnas encontradas en la base de datos:", list(df.columns))
        return
    
    # Eliminar filas duplicadas y mantener el último estado
    df = df.sort_values(by=['Codigo'], ascending=[True]).drop_duplicates(subset=['Codigo'], keep='last')
    
    # Excluir barriles que ya fueron despachados
    df = df[df['Estado'] != 'Despachado']
    
    # Filtrar barriles en "Cuarto Frío"
    df_cuarto_frio = df[df['Estado'] == 'Cuarto Frío'].copy()
    
    # Extraer litros del código (dos primeros dígitos) y convertir a número
    df_cuarto_frio['Litros'] = pd.to_numeric(df_cuarto_frio['Codigo'].str[:2], errors='coerce')
    
    # Eliminar filas con valores nulos en Litros
    df_cuarto_frio = df_cuarto_frio.dropna(subset=['Litros'])
    
    # Convertir a enteros
    df_cuarto_frio['Litros'] = df_cuarto_frio['Litros'].astype(int)
    
    if df_cuarto_frio.empty:
        st.warning("No hay barriles en 'Cuarto Frío' disponibles para el reporte.")
        return
    
    # Calcular litros por estilo
    litros_por_estilo = df_cuarto_frio.groupby('Estilo')['Litros'].sum().reset_index()
    
    st.subheader("Litros por Estilo (Solo en Cuarto Frío)")
    st.dataframe(litros_por_estilo)
    
    # Calcular litros totales
    litros_totales = df_cuarto_frio['Litros'].sum()
    st.write(f"**Litros Totales en Cuarto Frío:** {litros_totales} L")
    
    # Gráfico de distribución
    fig = px.pie(df_cuarto_frio, names='Estilo', values='Litros', title="Distribución de Litros en Cuarto Frío")
    st.plotly_chart(fig)

# Interfaz principal de la aplicación
st.title("📊 Reportes de la Cervecería")
reporte_barriles(df_barriles)
