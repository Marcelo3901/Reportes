import streamlit as st
import pandas as pd
import plotly.express as px
import urllib.parse

# URL base de la hoja de cálculo en Google Sheets (debe ser un enlace público CSV)
BASE_URL = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/gviz/tq?tqx=out:csv&sheet="

# Nombres de hojas
SHEETS = {
    "InventarioLatas": "InventarioLatas",
    "DatosM": "DatosM",
    "VLatas": "VLatas",
    "RClientes": "RClientes"
}

# Función para cargar datos desde Google Sheets
def cargar_datos(hoja_nombre):
    try:
        url = BASE_URL + urllib.parse.quote(SHEETS[hoja_nombre])
        df = pd.read_csv(url, dtype=str).dropna(how='all')
        df.columns = df.columns.str.strip()
        df = df.loc[:, ~df.columns.duplicated()]
        if df.empty or df.shape[1] < 2 or all(df.columns.str.contains("Unnamed")):
            st.warning(f"No se encontraron datos en {hoja_nombre}.")
            return pd.DataFrame()
        return df.copy()
    except Exception as e:
        st.error(f"Error al cargar {hoja_nombre}: {e}")
        return pd.DataFrame()

# Cargar datos
hojas = {nombre: cargar_datos(nombre) for nombre in SHEETS}

def reporte_barriles(df):
    st.subheader("Estado de los Barriles y Litros Totales")
    
    columnas_mapeo = {
        "Código": "Codigo", "Estilo.1": "Estilo", "Cliente.1": "Cliente",
        "Estado.1": "Estado", "Responsable.1": "Responsable", "Observaciones.2": "Observaciones"
    }
    df.rename(columns=columnas_mapeo, inplace=True)
    df = df.loc[:, ~df.columns.duplicated()]
    
    if {'Codigo', 'Estilo', 'Cliente', 'Estado'}.issubset(df.columns):
        df = df.sort_values(by='Codigo').drop_duplicates(subset='Codigo', keep='last')
        df_cuarto_frio = df[df['Estado'] == 'Cuarto Frío'].copy()
        df_cuarto_frio['Litros'] = pd.to_numeric(df_cuarto_frio['Codigo'].str[:2], errors='coerce').dropna().astype(int)
        
        if df_cuarto_frio.empty:
            st.warning("No hay barriles en 'Cuarto Frío'.")
            return
        
        litros_por_estilo = df_cuarto_frio.groupby('Estilo')['Litros'].sum().reset_index()
        st.subheader("Litros por Estilo en Cuarto Frío")
        st.dataframe(litros_por_estilo)
        
        st.write(f"**Litros Totales en Cuarto Frío:** {df_cuarto_frio['Litros'].sum()} L")
        st.plotly_chart(px.pie(litros_por_estilo, names='Estilo', values='Litros', title="Distribución de Litros"))
    else:
        st.warning("Faltan columnas necesarias.")

st.title("📊 Reportes de la Cervecería")
reporte_barriles(hojas["DatosM"])
