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
    if not df.empty and df.shape[1] >= 8:
        df = df.iloc[:, [0, 1, 3, 5, 6, 7, 8, 9]]  # Selección de columnas específicas
        df.columns = ['Código', 'Estilo', 'Cliente', 'Estado', 'Responsable', 'Observaciones', 'Fecha', 'Dias']
        
        # Filtrar último estado de cada barril
        df = df.sort_values(by=['Código', 'Fecha'], ascending=[True, False]).drop_duplicates(subset=['Código'], keep='first')
        
        # Excluir barriles despachados del inventario
        df = df[df['Estado'] != 'Despachado']
        
        # Filtrar barriles en "Cuarto Frío"
        df = df[df['Estado'] == 'Cuarto Frío']
        
        # Calcular litros según el código del barril
        df['Litros'] = df['Código'].astype(str).str[:2].astype(int)
        
        # Litros por estilo
        litros_por_estilo = df.groupby('Estilo')['Litros'].sum().reset_index()
        st.subheader("Litros por Estilo (Solo en Cuarto Frío)")
        st.dataframe(litros_por_estilo)
        
        # Litros totales
        litros_totales = df['Litros'].sum()
        st.write(f"**Litros Totales en Cuarto Frío:** {litros_totales} L")
        
        fig = px.pie(df, names='Estado', title="Distribución de Barriles en Cuarto Frío")
        st.plotly_chart(fig)
    else:
        st.warning("No hay datos de barriles disponibles o falta la columna correspondiente.")

# Interfaz principal de la aplicación
st.title("📊 Reportes de la Cervecería")
reporte_barriles(df_barriles)
