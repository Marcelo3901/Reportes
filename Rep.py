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
        st.write(f"Cargando datos desde: {url}")  # Depuración
        df = pd.read_csv(url, dtype=str)
        df = df.dropna(how='all')  # Eliminar filas completamente vacías
        df.columns = df.columns.str.strip()  # Limpiar nombres de columnas
        if df.empty or df.shape[1] < 2 or all(df.columns.str.contains("Unnamed")):
            st.warning(f"No se encontraron datos en la hoja {hoja_nombre} o la hoja está vacía.")
            return pd.DataFrame()
        st.success(f"Datos de {hoja_nombre} cargados correctamente.")
        return df
    except Exception as e:
        st.error(f"Error al cargar datos de {hoja_nombre}: {e}")
        return pd.DataFrame()

# Cargar cada hoja de la base de datos
df_latas = cargar_datos("InventarioLatas")
df_barriles = cargar_datos("DatosM")
df_ventas_latas = cargar_datos("VLatas")
df_clientes = cargar_datos("RClientes")

# Reporte de inventario de latas
def reporte_inventario_latas(df):
    st.subheader("Inventario de Latas en Cuarto Frío")
    columnas_requeridas = {"Estilo", "Cantidad", "Lote", "Responsable"}
    if not df.empty and columnas_requeridas.issubset(df.columns):
        df['Cantidad'] = pd.to_numeric(df['Cantidad'], errors='coerce').fillna(0).astype(int)
        st.dataframe(df)
        fig = px.bar(df, x='Estilo', y='Cantidad', color='Lote', title="Cantidad de Latas por Estilo y Lote")
        st.plotly_chart(fig)
    else:
        st.warning("No hay datos de latas disponibles o faltan columnas esperadas.")

# Reporte de barriles
def reporte_barriles(df):
    st.subheader("Estado de los Barriles")
    if not df.empty and 'Estado' in df.columns:
        estados = df['Estado'].value_counts().to_dict()
        for estado, cantidad in estados.items():
            st.write(f"**{estado}:** {cantidad} barriles")
        
        fig = px.pie(df, names='Estado', title="Distribución de Barriles por Estado")
        st.plotly_chart(fig)
    else:
        st.warning("No hay datos de barriles disponibles o falta la columna 'Estado'.")

# Reporte de ventas de latas
def reporte_ventas_latas(df):
    st.subheader("Ventas y Despachos de Latas")
    if not df.empty and {'Cliente', 'Cantidad', 'Estado'}.issubset(df.columns):
        df['Cantidad'] = pd.to_numeric(df['Cantidad'], errors='coerce').fillna(0).astype(int)
        fig = px.bar(df, x='Cliente', y='Cantidad', color='Estado', title="Ventas de Latas por Cliente")
        st.plotly_chart(fig)
    else:
        st.warning("No hay datos de ventas de latas disponibles o faltan columnas esperadas.")

# Lista de clientes
def reporte_clientes(df):
    st.subheader("Lista de Clientes Registrados")
    if not df.empty and {'Nombre', 'Dirección'}.issubset(df.columns):
        st.dataframe(df[['Nombre', 'Dirección']])
    else:
        st.warning("No hay clientes registrados o faltan columnas esperadas.")

# Alertas de barriles en clientes
def generar_alertas(df):
    st.subheader("Alertas de Barriles")
    if not df.empty and 'Días en Cliente' in df.columns:
        df['Días en Cliente'] = pd.to_numeric(df['Días en Cliente'], errors='coerce').fillna(0).astype(int)
        alertas = df[df['Días en Cliente'] > 180]
        if not alertas.empty:
            st.write("🔴 Barriles con clientes por más de 6 meses:")
            st.dataframe(alertas)
        
        if 'Capacidad' in df.columns:
            df['Capacidad'] = pd.to_numeric(df['Capacidad'], errors='coerce').fillna(0)
            if df['Capacidad'].sum() < 200:
                st.write("⚠️ Riesgo de quiebre de stock: menos de 200L disponibles.")
    else:
        st.warning("No hay datos disponibles para generar alertas o falta la columna 'Días en Cliente'.")

# Interfaz principal de la aplicación
st.title("📊 Reportes de la Cervecería")
reporte_inventario_latas(df_latas)
reporte_barriles(df_barriles)
reporte_ventas_latas(df_ventas_latas)
reporte_clientes(df_clientes)
generar_alertas(df_barriles)
