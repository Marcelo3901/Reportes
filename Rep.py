import pandas as pd
import streamlit as st

# Intentar importar unidecode; si no está instalado, definir una función que simplemente devuelva el mismo texto.
try:
    from unidecode import unidecode
except ModuleNotFoundError:
    st.warning("El módulo 'unidecode' no se encontró. Se usará una función de 'unidecode' que no modifica el texto.")
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
        st.write("URL utilizada para obtener los datos:", url)
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()  # Limpiar espacios en los nombres de las columnas.
        
        st.write("Columnas detectadas:", list(df.columns))
        st.write("Vista previa de las primeras filas:")
        st.write(df.head(10))
        
        # Verificar que existan las columnas requeridas.
        required = ["Código", "Marca temporal", "Estado", "Estado.1", "Estilo", "Estilo.1"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            st.error(f"Faltan columnas requeridas: {missing}")
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

# Obtener los datos.
df = obtener_datos_de_hoja(sheet_url, sheet_name)

st.write("Dimensiones del DataFrame:", df.shape)

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
    
    st.write("Valores únicos en Estado_final:", df["Estado_final"].unique())
    
    # Filtrar solo los registros cuyo Estado_final sea "en cuarto frío".
    df_cf = df[df["Estado_final"] == "en cuarto frío"]
    st.write("Número de registros con Estado 'en cuarto frío':", df_cf.shape[0])
    
    # Función para determinar la capacidad (litros) según los dos primeros dígitos del código.
    def obtener_capacidad(Código):
        codigo_str = str(Código).strip()
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
    litros_por_estilo = df_cf.groupby("Estilo_final")["Litros"].sum()
    
    # Mostrar resultados en Streamlit.
    st.title("Reporte de Inventario de Barriles en Cuarto Frío")
    st.subheader("Resumen del Inventario")
    st.write(f"**Barriles Totales:** {total_barriles}")
    st.write(f"**Litros Totales:** {litros_totales} litros")
    
    st.subheader("Litros por Estilo")
    st.write(litros_por_estilo)
    
    st.subheader("Detalle del Inventario")
    st.write(df_cf[["Marca temporal", "Código", "Estilo_final", "Estado_final", "Litros"]])
else:
    st.error("No se cargaron datos.")

# --- Visualizaciones adicionales ---
st.markdown("---")
st.subheader("Visualizaciones Adicionales")

# 1. Scatter Plot: Relación entre el código numérico y los litros.
# Convertir 'Código' a numérico (si es posible). Los valores que no puedan convertirse se marcarán como NaN.
try:
    df_cf["Código_num"] = pd.to_numeric(df_cf["Código"], errors="coerce")
    import plotly.express as px
    fig_scatter = px.scatter(
        df_cf,
        x="Código_num",
        y="Litros",
        color="Estilo_final",
        title="Scatter Plot: Código numérico vs Litros",
        labels={"Código_num": "Código (numérico)", "Litros": "Litros"}
    )
    st.plotly_chart(fig_scatter)
except Exception as e:
    st.warning(f"No se pudo crear el scatter plot: {e}")

# 2. Histograma: Distribución de los litros.
try:
    fig_hist = px.histogram(
        df_cf,
        x="Litros",
        nbins=10,
        title="Histograma de Litros"
    )
    st.plotly_chart(fig_hist)
except Exception as e:
    st.warning(f"No se pudo crear el histograma: {e}")

# 3. Box Plot: Distribución de Litros por Estilo.
try:
    fig_box = px.box(
        df_cf,
        x="Estilo_final",
        y="Litros",
        title="Box Plot de Litros por Estilo"
    )
    st.plotly_chart(fig_box)
except Exception as e:
    st.warning(f"No se pudo crear el box plot: {e}")

# 4. Heatmap: Matriz de correlación de las columnas numéricas.
try:
    # Seleccionar solo las columnas numéricas (por ejemplo, 'Litros' y 'Código_num' si está disponible)
    numeric_df = df_cf.select_dtypes(include=["number"])
    import seaborn as sns
    import matplotlib.pyplot as plt
    fig_heat, ax = plt.subplots(figsize=(4,3))
    sns.heatmap(numeric_df.corr(), annot=True, cmap="coolwarm", ax=ax)
    st.pyplot(fig_heat)
except Exception as e:
    st.warning(f"No se pudo crear el heatmap: {e}")

# 5. Gráfico de Área: Evolución diaria del inventario (si la columna 'Marca temporal' está disponible).
try:
    df_time = df.copy()
    df_time['Fecha'] = df_time['Marca temporal'].dt.date  # Extraer solo la fecha
    inventario_diario = df_time.groupby('Fecha').size()
    st.markdown("### Gráfico de Área: Inventario Diario")
    st.area_chart(inventario_diario)
except Exception as e:
    st.warning(f"No se pudo crear el gráfico de área: {e}")

# 6. Bubble Chart: Gráfico de dispersión con burbujas, usando 'Código_num' y 'Litros'.
try:
    fig_bubble = px.scatter(
        df_cf,
        x="Código_num",
        y="Litros",
        size="Litros",
        color="Estilo_final",
        title="Bubble Chart: Código numérico vs Litros",
        labels={"Código_num": "Código (numérico)", "Litros": "Litros"}
    )
    st.plotly_chart(fig_bubble)
except Exception as e:
    st.warning(f"No se pudo crear el bubble chart: {e}")
