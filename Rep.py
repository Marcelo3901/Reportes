import pandas as pd
import streamlit as st
import altair as alt
import matplotlib.pyplot as plt
import seaborn as sns
from gspread_dataframe import get_as_dataframe

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

    st.subheader("Litros por Estilo")
    st.write(df_litros)
    
    st.subheader("Resumen del Inventario")
    st.write(f"**Barriles Totales:** {total_barriles}")
    st.write(f"**Litros Totales:** {litros_totales} litros")

colores = {
    "Golden": "#f6ff33",
    "IPA": "#20cb80",
    "Barley Wine": "#6113c5",
    "Session IPA": "#65f859",
    "Trigo": "#ecc00f",
    "Vienna Lager": "#e87118",
    "Stout": "#3f3e3d",
    "Otros": "#bbb6b2",
    "Amber": "#f52615",
    "Maracuya": "#e7e000",
    "Brown Ale Cafe": "#135b08"
}

# Verificar si df_litros tiene datos antes de graficar
if not df_litros.empty:
    st.markdown("---")
    st.subheader("Barriles por Estilo")

    # Crear gráfico con Altair
    chart = alt.Chart(df_litros).mark_bar().encode(
        x=alt.X("Estilo", sort="-y"),
        y="Barriles",
        color=alt.Color("Estilo", scale=alt.Scale(domain=list(colores.keys()), range=list(colores.values()))),
        tooltip=["Estilo", "Barriles"]
    ).properties(width=600, height=400)

    # Mostrar en Streamlit
    st.altair_chart(chart, use_container_width=True)
     
else:
    st.error("No se cargaron datos.")

# Conectar con Google Sheets sin autenticación usando pandas
sheet_id = "1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY"
gid_inventario = "1870686258"
gid_vlatas = "1581220149"

sheet_url_inventario = f"https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/export?format=csv&gid=1870686258"
sheet_url_vlatas = f"https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/export?format=csv&gid=1581220149"

df_inventario = pd.read_csv(sheet_url_inventario)
df_despachos = pd.read_csv(sheet_url_vlatas)

# Verificar las columnas disponibles
print("Columnas disponibles en df_inventario:", df_inventario.columns)
print("Columnas disponibles en df_despachos:", df_despachos.columns)

if "Cantidad" in df_inventario.columns:
    df_inventario["Cantidad"] = pd.to_numeric(df_inventario["Cantidad"], errors='coerce')
else:
    print("Error: La columna 'Cantidad' no existe en df_inventario")

if "Cantidad" in df_despachos.columns:
    df_despachos["Cantidad"] = pd.to_numeric(df_despachos["Cantidad"], errors='coerce')
else:
    print("Error: La columna 'Cantidad' no existe en df_despachos")

# Agrupar por Estilo y Lote
if "Estilo" in df_inventario.columns and "Lote" in df_inventario.columns:
    inventario_agrupado = df_inventario.groupby(["Estilo", "Lote"]) ["Cantidad"].sum().reset_index()
else:
    print("Error: Las columnas 'Estilo' o 'Lote' no existen en df_inventario")
    inventario_agrupado = pd.DataFrame()

if "Estilo" in df_despachos.columns and "Lote" in df_despachos.columns:
    despachos_agrupado = df_despachos.groupby(["Estilo", "Lote"]) ["Cantidad"].sum().reset_index()
else:
    print("Error: Las columnas 'Estilo' o 'Lote' no existen en df_despachos")
    despachos_agrupado = pd.DataFrame()

# Combinar datos y calcular inventario actual
if not inventario_agrupado.empty and not despachos_agrupado.empty:
    inventario_total = pd.merge(inventario_agrupado, despachos_agrupado, on=["Estilo", "Lote"], how="left", suffixes=("_ingreso", "_salida"))
    inventario_total["Cantidad_salida"].fillna(0, inplace=True)
    inventario_total["Inventario"] = inventario_total["Cantidad_ingreso"] - inventario_total["Cantidad_salida"]
    inventario_total = inventario_total[inventario_total["Inventario"] > 0]
else:
    inventario_total = pd.DataFrame()
    print("Error: No se pudo calcular el inventario total")

# Asignar colores a cada estilo
if not inventario_total.empty:
    estilos_unicos = inventario_total["Estilo"].unique()
    colores = sns.color_palette("husl", len(estilos_unicos))
    color_dict = dict(zip(estilos_unicos, colores))

    # Crear gráfico de barras
    plt.figure(figsize=(10, 6))
    sns.barplot(x="Inventario", y="Estilo", data=inventario_total, hue="Estilo", palette=color_dict, dodge=False)
    plt.xlabel("Cantidad Disponible")
    plt.ylabel("Estilo de Cerveza")
    plt.title("Inventario de Latas en Cuarto Frío")
    plt.legend(title="Estilo")
    plt.show()
else:
    print("No hay datos disponibles para generar el gráfico.")

# Código para manejar el inventario de latas basado en ambas hojas
if "Capacidad" in df_inventario.columns and "Capacidad" in df_despachos.columns:
    inventario_agrupado_latas = df_inventario.groupby(["Estilo", "Lote", "Capacidad"]) ["Cantidad"].sum().reset_index()
    despachos_agrupado_latas = df_despachos.groupby(["Estilo", "Lote", "Capacidad"]) ["Cantidad"].sum().reset_index()
    
    inventario_total_latas = pd.merge(inventario_agrupado_latas, despachos_agrupado_latas, on=["Estilo", "Lote", "Capacidad"], how="left", suffixes=("_ingreso", "_salida"))
    inventario_total_latas["Cantidad_salida"].fillna(0, inplace=True)
    inventario_total_latas["Inventario"] = inventario_total_latas["Cantidad_ingreso"] - inventario_total_latas["Cantidad_salida"]
    inventario_total_latas = inventario_total_latas[inventario_total_latas["Inventario"] > 0]
else:
    print("Error: No se encontraron las columnas necesarias para calcular el inventario de latas")
    inventario_total_latas = pd.DataFrame()

# Gráfico de inventario de latas por capacidad
if not inventario_total_latas.empty:
    plt.figure(figsize=(12, 7))
    sns.barplot(x="Inventario", y="Estilo", hue="Capacidad", data=inventario_total_latas, dodge=True)
    plt.xlabel("Cantidad Disponible")
    plt.ylabel("Estilo de Cerveza")
    plt.title("Inventario de Latas por Capacidad")
    plt.legend(title="Capacidad (ml)")
    plt.show()
else:
    print("No hay datos disponibles para generar el gráfico de latas.")




###########


import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime, timedelta

# Función auxiliar: devuelve el primer valor no vacío entre los argumentos.
def primer_no_vacio(*args):
    for a in args:
        if pd.notna(a) and str(a).strip() != "":
            return str(a).strip()
    return ""

# Función para obtener los datos desde la hoja pública de Google Sheets en formato CSV.
def obtener_datos_de_hoja(sheet_url, sheet_name):
    try:
        url = f"{sheet_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()

        requeridas = ["Código", "Marca temporal", "Estado", "Estado.1", "Estilo", "Estilo.1", "Cliente", "Cliente.1"]
        faltantes = [col for col in requeridas if col not in df.columns]
        if faltantes:
            st.error(f"Faltan columnas requeridas: {faltantes}")
            return pd.DataFrame()

        df = df[df["Código"].notna()]
        df = df[df["Código"].astype(str).str.strip() != ""]

        return df
    except Exception as e:
        st.error(f"Error al obtener datos: {e}")
        return pd.DataFrame()

# Parámetros de la hoja de Google Sheets.
sheet_url = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY"
sheet_name = "DatosM"

# Obtener los datos.
df = obtener_datos_de_hoja(sheet_url, sheet_name)

if not df.empty:
    # Convertir "Marca temporal" a datetime.
    try:
        df['Marca temporal'] = pd.to_datetime(df['Marca temporal'], format='%d/%m/%Y %H:%M:%S')
    except Exception as e:
        st.error(f"Error al convertir 'Marca temporal': {e}")

    # Ordenar y conservar solo el registro más reciente por "Código".
    df = df.sort_values('Marca temporal', ascending=False)
    df = df.drop_duplicates(subset='Código', keep='first')

    # Crear columnas combinadas.
    df["Estado_final"] = df.apply(lambda row: primer_no_vacio(row.get("Estado", ""), row.get("Estado.1", "")), axis=1)
    df["Estilo_final"] = df.apply(lambda row: primer_no_vacio(row.get("Estilo", ""), row.get("Estilo.1", "")), axis=1)

    # Normalizar texto.
    df["Estado_final"] = df["Estado_final"].str.strip().str.lower()
    df["Estilo_final"] = df["Estilo_final"].str.strip()

    # Filtrar solo registros con estado "despacho".
    df_filtrado = df[df["Estado"].str.strip().str.lower() == "despacho"]

    # Función para determinar la capacidad (litros) según el código.
    def obtener_capacidad(codigo):
        codigo_str = str(codigo).strip()
        if codigo_str.startswith("20"):
            return 20
        elif codigo_str.startswith("30"):
            return 30
        elif codigo_str.startswith("58"):
            return 58
        else:
            return 0

    df_filtrado["Litros"] = df_filtrado["Código"].apply(obtener_capacidad)

    # Selección del tipo de reporte.
    st.sidebar.header("Opciones de Reporte")
    reporte_opcion = st.sidebar.selectbox("Seleccionar tipo de reporte:", ["Reporte Total", "Rango de Fechas"])

    if reporte_opcion == "Reporte Total":
        fecha_inicio = datetime.today().replace(day=1)  # Primer día del mes actual
        fecha_fin = datetime.today()  # Hoy
    else:
        # Selección de rango de fechas.
        fecha_inicio = st.sidebar.date_input("Fecha Inicial", datetime.today() - timedelta(days=30))
        fecha_fin = st.sidebar.date_input("Fecha Final", datetime.today())

    # Convertir fechas seleccionadas a datetime para filtrado.
    fecha_inicio = pd.to_datetime(fecha_inicio)
    fecha_fin = pd.to_datetime(fecha_fin) + timedelta(days=1)  # Incluir el día completo.

    # Filtrar datos dentro del rango de fechas.
    df_filtrado = df_filtrado[(df_filtrado["Marca temporal"] >= fecha_inicio) & (df_filtrado["Marca temporal"] < fecha_fin)]

    # Agrupar datos por Cliente y Estilo.
    ventas_por_cliente = df_filtrado.groupby(["Cliente", "Estilo_final"])["Litros"].sum()
    ventas_por_barriles = df_filtrado.groupby(["Cliente", "Estilo_final"]).size()

    # Crear DataFrame con ventas.
    df_ventas = pd.DataFrame({
        "Litros": ventas_por_cliente,
        "Barriles": ventas_por_barriles
    }).reset_index()

    # Mostrar el reporte.
    st.subheader("Reporte de Ventas")
    st.write(df_ventas)

    # Crear gráfico de barriles despachados por cliente.
    ventas_por_cliente = df_filtrado.groupby('Cliente').size().reset_index(name='Barriles')

    chart = alt.Chart(ventas_por_cliente).mark_bar().encode(
        x=alt.X('Cliente', sort='-y'),
        y='Barriles',
        tooltip=['Cliente', 'Barriles']
    ).properties(width=600, height=400)

    st.markdown("---")
    st.subheader("Gráfico de Barriles Despachados por Cliente")
    st.altair_chart(chart, use_container_width=True)

else:
    st.error("No se cargaron datos.")






########





# Función para obtener los datos desde la hoja pública de Google Sheets en formato CSV.
def obtener_datos_de_hoja(sheet_url, sheet_name):
    try:
        url = f"{sheet_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        
        # Verificar que existan las columnas requeridas.
        requeridas = ["Código", "Marca temporal", "Estado", "Cliente", "Estilo"]
        faltantes = [col for col in requeridas if col not in df.columns]
        if faltantes:
            st.error(f"Faltan columnas requeridas: {faltantes}")
            return pd.DataFrame()
        
        df = df[df["Código"].notna() & df["Cliente"].notna() & df["Estado"].notna()]
        df['Marca temporal'] = pd.to_datetime(df['Marca temporal'], errors='coerce')
        df = df.dropna(subset=['Marca temporal'])
        
        return df
    except Exception as e:
        st.error(f"Error al obtener datos: {e}")
        return pd.DataFrame()

# Parámetros: URL base de la hoja y nombre de la hoja.
sheet_url = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY"
sheet_name = "DatosM"

df = obtener_datos_de_hoja(sheet_url, sheet_name)

if not df.empty:
    df_despachos = df[df["Estado"].str.lower().str.strip() == "despacho"].copy()
    
    # Calcular la capacidad de los barriles
def obtener_capacidad(codigo):
        codigo_str = str(codigo).strip()
        if codigo_str.startswith("20"):
            return 20
        elif codigo_str.startswith("30"):
            return 30
        elif codigo_str.startswith("58"):
            return 58
        else:
            return 0

df_despachos["Litros"] = df_despachos["Código"].apply(obtener_capacidad)

df_reporte = df_despachos.groupby(["Cliente", "Estilo"]).agg({"Litros": "sum", "Código": "count"}).reset_index()
df_reporte.rename(columns={"Código": "Barriles"}, inplace=True)

st.subheader("📊 Reporte de Ventas")
st.write(df_reporte)

# Gráfico de litros despachados por cliente
st.subheader("Litros Despachados por Cliente")
chart_litros = alt.Chart(df_reporte).mark_bar().encode(
    x=alt.X("Cliente", sort="-y"),
    y="Litros",
    color="Cliente",
    tooltip=["Cliente", "Litros"]
).properties(width=600, height=400)
st.altair_chart(chart_litros, use_container_width=True)

# Gráfico de pastel de estilos más vendidos
st.subheader("Distribución de Estilos Vendidos")
fig, ax = plt.subplots()
ventas_por_estilo = df_reporte.groupby("Estilo")["Litros"].sum()
ax.pie(ventas_por_estilo, labels=ventas_por_estilo.index, autopct='%1.1f%%', startangle=90, colors=plt.cm.Paired.colors)
ax.axis("equal")
st.pyplot(fig)

# Gráfico de líneas de tendencia de despachos en el tiempo
st.subheader("Tendencia de Despachos en el Tiempo")
df_despachos["Fecha"] = df_despachos["Marca temporal"].dt.date
ventas_tiempo = df_despachos.groupby("Fecha")["Barriles"].sum().reset_index()
chart_tendencia = alt.Chart(ventas_tiempo).mark_line(point=True).encode(
    x="Fecha:T",
    y="Barriles:Q",
    tooltip=["Fecha", "Barriles"]
).properties(width=600, height=400)
st.altair_chart(chart_tendencia, use_container_width=True)

# Comparación de ventas con meses anteriores
st.subheader("Comparación con Meses Anteriores")
df_despachos["Mes"] = df_despachos["Marca temporal"].dt.to_period("M")
ventas_mensuales = df_despachos.groupby("Mes")["Barriles"].sum().reset_index()
chart_comparacion = alt.Chart(ventas_mensuales).mark_bar().encode(
    x="Mes:T",
    y="Barriles:Q",
    tooltip=["Mes", "Barriles"]
).properties(width=600, height=400)
st.altair_chart(chart_comparacion, use_container_width=True)

else:
    st.error("No hay datos de despachos para mostrar.")
