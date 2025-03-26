import pandas as pd
import streamlit as st

# Intentar importar unidecode; si no está instalado, definir una función que simplemente devuelva el mismo texto.
try:
    from unidecode import unidecode
except ModuleNotFoundError:
    def unidecode(text):
        return text

# Función auxiliar: devuelve el primer valor no vacío entre los argumentos.
def primer_no_vacio(*args):
    for a in args:
        if pd.notna(a) and str(a).strip() != "":
            return str(a).strip()
    return ""

# Función para obtener los datos desde la hoja pública de Google Sheets en formato CSV.
def obtener_datos_de_hoja(sheet_url, sheet_name):
    try:
        # Construir la URL para obtener el CSV (asegúrate de que la hoja esté publicada).
        url = f"{sheet_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()  # Limpiar espacios en los nombres de las columnas.
        
        # Verificar que existan las columnas requeridas.
        requeridas = ["Código", "Marca temporal", "Estado", "Estado.1", "Estilo", "Estilo.1"]
        faltantes = [col for col in requeridas if col not in df.columns]
        if faltantes:
            st.error(f"Faltan columnas requeridas: {faltantes}")
            return pd.DataFrame()
        
        # Eliminar filas donde "Código" sea nulo o vacío.
        df = df[df["Código"].notna()]
        df = df[df["Código"].astype(str).str.strip() != ""]
        
        return df
    except Exception as e:
        st.error(f"Error al obtener datos: {e}")
        return pd.DataFrame()

# Parámetros: URL base de la hoja y nombre de la hoja (deben coincidir exactamente).
sheet_url = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY"
sheet_name = "DatosM"  # Verifica que el nombre coincida exactamente con el de la pestaña.

# Encabezado principal con estilo personalizado.
st.markdown("<h1 style='text-align: center; color: #2c3e50; font-family: Verdana;'>Reporte de Inventario de Barriles en Cuarto Frío</h1>", unsafe_allow_html=True)

# Obtener los datos.
df = obtener_datos_de_hoja(sheet_url, sheet_name)

if not df.empty:
    # Convertir "Marca temporal" a datetime.
    try:
        df['Marca temporal'] = pd.to_datetime(df['Marca temporal'], format='%d/%m/%Y %H:%M:%S')
    except Exception as e:
        st.error(f"Error al convertir 'Marca temporal': {e}")
    
    # Ordenar por "Marca temporal" descendente y conservar solo el registro más reciente por "Código".
    df = df.sort_values('Marca temporal', ascending=False)
    df = df.drop_duplicates(subset='Código', keep='first')
    
    # Crear columnas "Estado_final" y "Estilo_final" combinando las variantes existentes.
    df["Estado_final"] = df.apply(lambda row: primer_no_vacio(row.get("Estado", ""), row.get("Estado.1", "")), axis=1)
    df["Estilo_final"] = df.apply(lambda row: primer_no_vacio(row.get("Estilo", ""), row.get("Estilo.1", "")), axis=1)
    
    # Normalizar: quitar espacios, pasar a minúsculas y eliminar acentos (si unidecode está disponible).
    df["Estado_final"] = df["Estado_final"].str.strip().str.lower().apply(unidecode)
    df["Estilo_final"] = df["Estilo_final"].str.strip().apply(unidecode)
    
    # Filtrar solo los registros cuyo Estado_final sea "en cuarto frío".
    df_cf = df[df["Estado_final"] == "en cuarto frío"]
    
    # Función para determinar la capacidad (litros) según los dos primeros dígitos del código.
    def obtener_capacidad(codigo):
        codigo_str = str(codigo).strip()
        if codigo_str.startswith("20"):
            return 20
        elif codigo_str.startswith("30"):
            return 30
        elif codigo_str.startswith("58"):
            return 58
        else:
            return 0  # Si no es un código reconocido.
    
    # Calcular la capacidad de cada barril y almacenarla en la columna "Litros".
    df_cf["Litros"] = df_cf["Código"].apply(obtener_capacidad)
    
    # Calcular totales.
    total_barriles = df_cf.shape[0]
    litros_totales = df_cf["Litros"].sum()
    
    # Agrupar por "Estilo_final" para obtener la suma de litros y el número de barriles.
    litros_por_estilo = df_cf.groupby("Estilo_final")["Litros"].sum()
    barriles_por_estilo = df_cf.groupby("Estilo_final").size()
    
    # Crear un DataFrame con ambas series.
    df_litros = pd.DataFrame({
        "Litros": litros_por_estilo,
        "Barriles": barriles_por_estilo
    }).reset_index()
    df_litros.columns = ["Estilo", "Litros", "Barriles"]
    
    # Agregar una columna "Alerta" que muestre un símbolo si los litros son menores a 200.
    df_litros["Alerta"] = df_litros["Litros"].apply(lambda x: "⚠️" if x < 200 else "")
    
    # Ordenar de mayor a menor según "Litros".
    df_litros = df_litros.sort_values(by="Litros", ascending=False)
    
    # Sección: Litros por Estilo (Tabla).
    st.markdown("<h3 style='color: #34495e; font-family: Verdana;'>Litros por Estilo</h3>", unsafe_allow_html=True)
    st.dataframe(df_litros.style\
               .background_gradient(cmap="YlOrRd", subset=["Litros"])\
               .set_properties(**{'font-family': 'Verdana', 'font-size': '14px'}), height=250)
    
    # Sección: Resumen del Inventario en dos columnas.
    st.markdown("<hr>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<h4 style='text-align: center; color: #e74c3c; font-family: Verdana;'>Barriles Totales</h4>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='text-align: center; color: #e74c3c; font-family: Verdana;'>{total_barriles}</h2>", unsafe_allow_html=True)
    with col2:
        st.markdown("<h4 style='text-align: center; color: #27ae60; font-family: Verdana;'>Litros Totales</h4>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='text-align: center; color: #27ae60; font-family: Verdana;'>{litros_totales} litros</h2>", unsafe_allow_html=True)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #2c3e50; font-family: Verdana;'>Detalle del Inventario</h3>", unsafe_allow_html=True)
    st.dataframe(df_cf[["Marca temporal", "Código", "Estilo_final", "Estado_final", "Litros"]])
    
    # Gráfico de Barras: Número de Barriles por Estilo (con Plotly Express).
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #2c3e50; font-family: Verdana;'>Gráfico de Barras: Número de Barriles por Estilo</h3>", unsafe_allow_html=True)
    try:
        import plotly.express as px
        fig_bar = px.bar(df_litros, x="Estilo", y="Barriles", color="Estilo",
                         title="Número de Barriles por Estilo",
                         text="Barriles",
                         labels={"Barriles": "Número de Barriles", "Estilo": "Estilo de Cerveza"})
        fig_bar.update_traces(texttemplate='%{text}', textposition='outside')
        fig_bar.update_layout(
            title_font=dict(family="Verdana", size=24, color="#2c3e50"),
            font=dict(family="Verdana", size=14, color="#34495e"),
            xaxis_title="Estilo",
            yaxis_title="Número de Barriles",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    except Exception as e:
        st.warning(f"No se pudo crear el gráfico de barras interactivo con Plotly: {e}")
    
    # Visualizaciones Temporales: Semanal y Mensual.
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #2c3e50; font-family: Verdana;'>Visualizaciones Temporales</h3>", unsafe_allow_html=True)
    
    # Usar df_cf para series temporales (ya contiene la columna "Litros").
    df_time = df_cf.copy()
    df_time['Fecha'] = df_time['Marca temporal'].dt.date  # Extraer solo la fecha
    df_time['Semana'] = df_time['Marca temporal'].dt.to_period('W').apply(lambda r: r.start_time)
    df_time['Mes'] = df_time['Marca temporal'].dt.to_period('M').apply(lambda r: r.start_time)
    
    produccion_semanal = df_time.groupby('Semana')['Litros'].sum().reset_index()
    produccion_mensual = df_time.groupby('Mes')['Litros'].sum().reset_index()
    
    st.markdown("<h4 style='color: #2c3e50; font-family: Verdana;'>Producción Semanal (Litros)</h4>", unsafe_allow_html=True)
    st.line_chart(produccion_semanal.set_index('Semana'))
    
    st.markdown("<h4 style='color: #2c3e50; font-family: Verdana;'>Producción Mensual (Litros)</h4>", unsafe_allow_html=True)
    st.line_chart(produccion_mensual.set_index('Mes'))
    
    # Gráficos interactivos con Plotly Express para visualizaciones temporales.
    try:
        fig_sem = px.line(produccion_semanal, x='Semana', y='Litros',
                          title='Producción Semanal (Litros)',
                          labels={'Semana': 'Semana', 'Litros': 'Litros'})
        fig_sem.update_layout(
            title_font=dict(family="Verdana", size=20, color="#2c3e50"),
            font=dict(family="Verdana", size=12, color="#34495e"),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_sem, use_container_width=True)
        
        fig_mes = px.line(produccion_mensual, x='Mes', y='Litros',
                          title='Producción Mensual (Litros)',
                          labels={'Mes': 'Mes', 'Litros': 'Litros'})
        fig_mes.update_layout(
            title_font=dict(family="Verdana", size=20, color="#2c3e50"),
            font=dict(family="Verdana", size=12, color="#34495e"),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_mes, use_container_width=True)
    except Exception as e:
        st.warning(f"No se pudieron crear los gráficos interactivos con Plotly: {e}")
    
else:
    st.error("No se cargaron datos.")
