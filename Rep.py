import pandas as pd
import streamlit as st
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

    st.markdown("---")
    st.subheader("Barriles por Estilo")
    st.bar_chart(df_litros.set_index("Estilo")["Barriles"])
     
else:
    st.error("No se cargaron datos.")

# Conectar con Google Sheets sin autenticación
sheet_url_inventario = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/export?format=csv&gid=0"
sheet_url_vlatas = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/export?format=csv&gid=123456789"  # GID correcto
sheet_url_datosm = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY/export?format=csv&gid=987654321"  # GID correcto

# Cargar datos
df_inventario = pd.read_csv(sheet_url_inventario)
df_despachos = pd.read_csv(sheet_url_vlatas)
df_datosm = pd.read_csv(sheet_url_datosm)

# Convertir la cantidad a numérico
df_inventario["Cantidad"] = pd.to_numeric(df_inventario["Cantidad"], errors='coerce')
df_despachos["Cantidad"] = pd.to_numeric(df_despachos["Cantidad"], errors='coerce')

# Agrupar por Estilo y Lote
inventario_agrupado = df_inventario.groupby(["Estilo", "Lote"])["Cantidad"].sum().reset_index()
despachos_agrupado = df_despachos.groupby(["Estilo", "Lote"])["Cantidad"].sum().reset_index()

# Combinar datos y calcular inventario actual
inventario_total = pd.merge(inventario_agrupado, despachos_agrupado, on=["Estilo", "Lote"], how="left", suffixes=("_ingreso", "_salida"))
inventario_total["Cantidad_salida"].fillna(0, inplace=True)
inventario_total["Inventario"] = inventario_total["Cantidad_ingreso"] - inventario_total["Cantidad_salida"]

# Filtrar solo estilos con inventario positivo
inventario_total = inventario_total[inventario_total["Inventario"] > 0]

# Asignar colores a cada estilo
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

