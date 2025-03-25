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

# Reporte de inventario de latas
def reporte_inventario_latas(df):
    st.subheader("Inventario de Latas en Cuarto Frío")
    if not df.empty and df.shape[1] >= 5:
        df.columns = ['A', 'B', 'C', 'D', 'E']  # Renombrar columnas por letras
        df['C'] = pd.to_numeric(df['C'], errors='coerce').fillna(0).astype(int)
        st.dataframe(df)
        fig = px.bar(df, x='B', y='C', color='D', title="Cantidad de Latas por Estilo y Lote")
        st.plotly_chart(fig)

# Reporte de barriles
def reporte_barriles(df):
    st.subheader("Estado de los Barriles")
    if not df.empty and df.shape[1] >= 8:
        df = df.iloc[:, [0, 1, 3, 5, 6, 7, 8, 9]]  # Selección de columnas específicas
        df.columns = ['A', 'B', 'D', 'F', 'G', 'H', 'I', 'J']  # Renombrar columnas por letras
        estados = df['G'].value_counts().to_dict()
        for estado, cantidad in estados.items():
            st.write(f"**{estado}:** {cantidad} barriles")
        fig = px.pie(df, names='G', title="Distribución de Barriles por Estado")
        st.plotly_chart(fig)

# Reporte de ventas de latas
def reporte_ventas_latas(df):
    st.subheader("Ventas y Despachos de Latas")
    if not df.empty and df.shape[1] >= 6:
        df.columns = ['A', 'B', 'C', 'D', 'E', 'F']  # Renombrar columnas por letras
        df['C'] = pd.to_numeric(df['C'], errors='coerce').fillna(0).astype(int)
        fig = px.bar(df, x='E', y='C', color='F', title="Ventas de Latas por Cliente")
        st.plotly_chart(fig)

# Lista de clientes
def reporte_clientes(df):
    st.subheader("Lista de Clientes Registrados")
    if not df.empty and df.shape[1] >= 2:
        df.columns = ['A', 'B']  # Renombrar columnas por letras
        st.dataframe(df[['A', 'B']])

# Alertas de barriles en clientes
def generar_alertas(df):
    st.subheader("Alertas de Barriles")
    if not df.empty and df.shape[1] >= 8:
        df = df.iloc[:, [0, 1, 3, 5, 6, 7, 8, 9]]  # Selección de columnas específicas
        df.columns = ['A', 'B', 'D', 'F', 'G', 'H', 'I', 'J']  # Renombrar columnas por letras
        df['J'] = pd.to_numeric(df['J'], errors='coerce').fillna(0).astype(int)
        alertas = df[df['J'] > 180]
        if not alertas.empty:
            st.write("🔴 Barriles con clientes por más de 6 meses:")
            st.dataframe(alertas)
        if 'E' in df.columns:
            df['E'] = pd.to_numeric(df['E'], errors='coerce').fillna(0)
            if df['E'].sum() < 200:
                st.write("⚠️ Riesgo de quiebre de stock: menos de 200L disponibles.")

# Interfaz principal de la aplicación
st.title("📊 Reportes de la Cervecería")
reporte_inventario_latas(df_latas)
reporte_barriles(df_barriles)
reporte_ventas_latas(df_ventas_latas)
reporte_clientes(df_clientes)
generar_alertas(df_barriles)
