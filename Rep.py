import pandas as pd
import streamlit as st

# Función para obtener los datos desde la hoja de Google Sheets pública en formato CSV
def obtener_datos_de_hoja(sheet_url):
    try:
        # Leer la hoja como CSV desde Google Sheets
        url = f"{sheet_url}/gviz/tq?tqx=out:csv&sheet=Hoja1"  # Cambiar "Hoja1" por el nombre de tu hoja
        df = pd.read_csv(url)
        
        # Limpiar los datos
        df.columns = df.columns.str.strip()  # Limpiar los espacios en los nombres de las columnas
        df.dropna(subset=["Código"], inplace=True)  # Eliminar filas donde no hay código de barril
        df = df[df["Código"].str.strip() != ""]  # Eliminar filas con códigos vacíos
        return df
    except Exception as e:
        st.warning(f"⚠️ No se pudieron cargar los datos: {e}")
        return pd.DataFrame()

# URL de la hoja de Google Sheets (pública)
sheet_url = 'https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY'

# Obtener los datos de la hoja
df = obtener_datos_de_hoja(sheet_url)

# Verificar si los datos se cargaron correctamente
if not df.empty:
    # Preprocesar los datos para el reporte de inventario
    df['Marca temporal'] = pd.to_datetime(df['Marca temporal'], format='%d/%m/%Y %H:%M:%S')
    df = df.sort_values('Marca temporal', ascending=False)  # Ordenar los registros por la marca temporal
    df = df.drop_duplicates(subset='Código', keep='first')  # Eliminar registros duplicados, manteniendo solo el más reciente

    # Determinar la capacidad de los barriles según los dos primeros dígitos del código
    def obtener_capacidad(codigo):
        if str(codigo).startswith('20'):
            return 20
        elif str(codigo).startswith('30'):
            return 30
        elif str(codigo).startswith('58'):
            return 58
        else:
            return 0  # Si no es un código conocido, asignamos 0 como capacidad desconocida

    df['Capacidad'] = df['Código'].apply(obtener_capacidad)

    # Calcular los litros totales y los litros por estilo
    litros_totales = df['Capacidad'].sum()
    litros_por_estilo = df.groupby('Estilo')['Capacidad'].sum()

    # Mostrar los resultados en Streamlit
    st.title('Reporte de Inventario de Barriles')

    # Reporte general
    st.subheader(f'Totales de Inventario (Cuarto Frío)')
    st.write(f'**Barriles Totales:** {df.shape[0]}')
    st.write(f'**Litros Totales:** {litros_totales} litros')

    # Reporte por estilo
    st.subheader('Litros por Estilo')
    st.write(litros_por_estilo)

    # Mostrar los datos en una tabla
    st.subheader('Detalle del Inventario')
    st.write(df[['Marca temporal', 'Código', 'Estilo', 'Estado', 'Capacidad']])

else:
    st.warning("⚠️ No se encontraron datos para mostrar.")
