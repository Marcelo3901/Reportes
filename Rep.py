import streamlit as st
import pandas as pd
import plotly.express as px

# URL de la base de datos en Google Sheets (debe ser un enlace público CSV)
URL_SHEET = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/edit?usp=sharing"

def cargar_datos():
    df = pd.read_csv(URL_SHEET)
    df['Capacidad'] = df['Código'].astype(str).str[:2].astype(int)
    df['Días en Cliente'] = pd.to_numeric(df['Días en Cliente'], errors='coerce')
    return df

# Reporte de ventas

def ventas_mensuales(df):
    st.subheader("Ventas Mensuales y en Tiempo Real")
    
    fig1 = px.bar(df, x='Cliente', y='Código', color='Estilo', title="Ventas por Cliente y Estilo")
    st.plotly_chart(fig1)
    
    fig2 = px.pie(df, names='Estilo', title="Distribución de Ventas por Estilo")
    st.plotly_chart(fig2)

# Reporte de inventario

def reporte_inventario(df):
    st.subheader("Estado del Inventario")
    estados = df["Estado"].value_counts().to_dict()
    for estado, cantidad in estados.items():
        st.write(f"**{estado}:** {cantidad} barriles")
    
    litros_por_estado = df.groupby("Estado")["Capacidad"].sum().to_dict()
    for estado, litros in litros_por_estado.items():
        st.write(f"**{estado}:** {litros} litros en total")

# Alarmas y alertas

def generar_alertas(df):
    st.subheader("Alertas")
    
    if not df[df['Días en Cliente'] > 180].empty:
        st.write("🔴 Barriles en poder del cliente por más de 6 meses:")
        st.dataframe(df[df['Días en Cliente'] > 180])
    
    if not df[df['Días en Cliente'] > 90].empty:
        st.write("⚠️ Barriles sucios por más de 3 semanas:")
        st.dataframe(df[df['Días en Cliente'] > 90])
    
    litros_totales = df["Capacidad"].sum()
    if litros_totales < 200:
        st.write("⚠️ Riesgo de quiebre de stock: menos de 200L disponibles.")

# Interfaz de la app
st.title("📊 Reportes de la Cervecería")
data = cargar_datos()
ventas_mensuales(data)
reporte_inventario(data)
generar_alertas(data)
