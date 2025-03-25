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
        
        # Verificar nombres duplicados y renombrarlos
        if df.columns.duplicated().any():
            df.columns = [f"{col}_{i}" if df.columns.duplicated()[i] else col for i, col in enumerate(df.columns)]
        
        st.write(f"Columnas de {hoja_nombre}: {df.columns.tolist()}")  # Debugging
        if df.empty or df.shape[1] < 2 or all(df.columns.str.contains("Unnamed")):
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()

# Cargar cada hoja de la base de datos
df_latas = cargar_datos("InventarioLatas")
df_barriles = cargar_datos("DatosM")
df_ventas_latas = cargar_datos("VLatas")
df_clientes = cargar_datos("RClientes")

   # Reporte de barriles
def reporte_barriles(df):
    st.subheader("Estado de los Barriles")
    if not df.empty:
        # Mostrar nombres reales de columnas para depuración
        st.write("Columnas disponibles en DatosM:", df.columns.tolist())
        
        # Buscar la columna que contiene los estados
        col_estado = next((col for col in df.columns if "estado" in col.lower()), None)
        if not col_estado:
            st.error("Error: No se encontró la columna 'Estado'. Verifica la hoja de cálculo.")
            return

        # Filtrar barriles no despachados de forma segura
        df = df[df[col_estado] != 'Despachado']

        estados = df[col_estado].value_counts().to_dict()
        for estado, cantidad in estados.items():
            st.write(f"**{estado}:** {cantidad} barriles")

        fig = px.pie(df, names=col_estado, title="Distribución de Barriles por Estado")
        st.plotly_chart(fig)


# Interfaz principal de la aplicación
st.title("📊 Reportes de la Cervecería")
reporte_inventario_latas(df_latas)
reporte_barriles(df_barriles)
reporte_ventas_latas(df_ventas_latas)
reporte_clientes(df_clientes)
generar_alertas(df_barriles)
