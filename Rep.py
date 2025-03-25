import streamlit as st
import pandas as pd
import plotly.express as px

# URL base de la hoja de cálculo en Google Sheets (debe ser un enlace público CSV)
BASE_URL = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/edit?usp=sharing"

# Cargar datos de cada hoja
def cargar_datos(hoja):
    try:
        url = BASE_URL + hoja
        df = pd.read_csv(url)
        return df.dropna()
    except Exception as e:
        st.error(f"Error al cargar datos de {hoja}: {e}")
        return pd.DataFrame()

# Cargar cada hoja de la base de datos
df_latas = cargar_datos("Inventario latas")
df_barriles = cargar_datos("Datos M")
df_ventas_latas = cargar_datos("VLatas")
df_clientes = cargar_datos("RClientes")

# Reporte de inventario de latas
def reporte_inventario_latas(df):
    st.subheader("Inventario de Latas en Cuarto Frío")
    if not df.empty:
        st.dataframe(df)
        fig = px.bar(df, x='Estilo', y='Cantidad', color='Lote', title="Cantidad de Latas por Estilo y Lote")
        st.plotly_chart(fig)
    else:
        st.warning("No hay datos de latas disponibles.")

# Reporte de barriles
def reporte_barriles(df):
    st.subheader("Estado de los Barriles")
    if not df.empty:
        estados = df["Estado"].value_counts().to_dict()
        for estado, cantidad in estados.items():
            st.write(f"**{estado}:** {cantidad} barriles")
        
        fig = px.pie(df, names='Estado', title="Distribución de Barriles por Estado")
        st.plotly_chart(fig)
    else:
        st.warning("No hay datos de barriles disponibles.")

# Reporte de ventas de latas
def reporte_ventas_latas(df):
    st.subheader("Ventas y Despachos de Latas")
    if not df.empty:
        fig = px.bar(df, x='Cliente', y='Cantidad', color='Estado', title="Ventas de Latas por Cliente")
        st.plotly_chart(fig)
    else:
        st.warning("No hay datos de ventas de latas disponibles.")

# Lista de clientes
def reporte_clientes(df):
    st.subheader("Lista de Clientes Registrados")
    if not df.empty:
        st.dataframe(df[['Nombre', 'Dirección']])
    else:
        st.warning("No hay clientes registrados.")

# Alertas de barriles en clientes
def generar_alertas(df):
    st.subheader("Alertas de Barriles")
    if not df.empty:
        df['Días en Cliente'] = pd.to_numeric(df['Días en Cliente'], errors='coerce')
        alertas = df[df['Días en Cliente'] > 180]
        if not alertas.empty:
            st.write("🔴 Barriles con clientes por más de 6 meses:")
            st.dataframe(alertas)
        
        if df['Capacidad'].sum() < 200:
            st.write("⚠️ Riesgo de quiebre de stock: menos de 200L disponibles.")
    else:
        st.warning("No hay datos disponibles para generar alertas.")

# Interfaz principal de la aplicación
st.title("📊 Reportes de la Cervecería")
reporte_inventario_latas(df_latas)
reporte_barriles(df_barriles)
reporte_ventas_latas(df_ventas_latas)
reporte_clientes(df_clientes)
generar_alertas(df_barriles)
