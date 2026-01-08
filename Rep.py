import pandas as pd
import streamlit as st
import altair as alt
import matplotlib.pyplot as plt
import seaborn as sns

# CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="REPORTES BARRILES", layout="centered")

st.markdown("<h1 style='text-align:center; color:#20cb80;'>🍺 REPORTE BARRILES Y LATAS CASTIZA</h1>", unsafe_allow_html=True)

# Intentar importar unidecode
try:
    from unidecode import unidecode
except ModuleNotFoundError:
    def unidecode(text):
        return text

def primer_no_vacio(*args):
    for a in args:
        if pd.notna(a) and str(a).strip() != "":
            return str(a).strip()
    return ""

def obtener_datos_de_hoja(sheet_url, sheet_name):
    try:
        url = f"{sheet_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()

        requeridas = ["Código", "Marca temporal", "Estado", "Estado.1", "Estilo", "Estilo.1"]
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

sheet_url = "https://docs.google.com/spreadsheets/d/1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY"
sheet_name = "DatosM"

df = obtener_datos_de_hoja(sheet_url, sheet_name)

if not df.empty:
    df['Marca temporal'] = pd.to_datetime(df['Marca temporal'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    df = df.sort_values('Marca temporal', ascending=False)
    df = df.drop_duplicates(subset='Código', keep='first')

    df["Estado_final"] = df.apply(lambda r: primer_no_vacio(r.get("Estado", ""), r.get("Estado.1", "")), axis=1)
    df["Estilo_final"] = df.apply(lambda r: primer_no_vacio(r.get("Estilo", ""), r.get("Estilo.1", "")), axis=1)

    df["Estado_final"] = df["Estado_final"].str.strip().str.lower().apply(unidecode)
    df["Estilo_final"] = df["Estilo_final"].str.strip().apply(unidecode)

    df_cf = df[df["Estado_final"] == "en cuarto frio"]

    def obtener_capacidad(codigo):
        codigo = str(codigo)
        if codigo.startswith("20"):
            return 20
        elif codigo.startswith("30"):
            return 30
        elif codigo.startswith("58"):
            return 58
        return 0

    df_cf["Litros"] = df_cf["Código"].apply(obtener_capacidad)

    # ==============================
    # 🔹 LITROS POR ESTILO (MODIFICADO)
    # ==============================

    total_barriles = df_cf.shape[0]
    litros_totales = df_cf["Litros"].sum()

    litros_por_estilo = df_cf.groupby("Estilo_final")["Litros"].sum()
    barriles_por_estilo = df_cf.groupby("Estilo_final").size()

    df_litros = pd.DataFrame({
        "Litros": litros_por_estilo,
        "Barriles": barriles_por_estilo
    }).reset_index()

    df_litros.columns = ["Estilo", "Litros", "Barriles"]

    df_litros["Alerta"] = df_litros["Litros"].apply(lambda x: "⚠️" if x < 200 else "")

    def codigos_en_alerta(estilo, litros):
        if litros >= 200:
            return ""
        codigos = df_cf.loc[df_cf["Estilo_final"] == estilo, "Código"].astype(str)
        return ", ".join(codigos)

    df_litros["Códigos en alerta"] = df_litros.apply(
        lambda row: codigos_en_alerta(row["Estilo"], row["Litros"]),
        axis=1
    )

    df_litros = df_litros.sort_values(by="Litros", ascending=False)

    st.subheader("Litros por Estilo")
    st.write(df_litros)

    st.subheader("Resumen del Inventario")
    st.write(f"**Barriles Totales:** {total_barriles}")
    st.write(f"**Litros Totales:** {litros_totales} litros")

    # ==============================
    # 🔹 GRÁFICO
    # ==============================

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
        "Maracuyá": "#e7e000",
        "Brown Ale Cafe": "#135b08"
    }

    st.markdown("---")
    st.subheader("Barriles por Estilo")

    chart = alt.Chart(df_litros).mark_bar().encode(
        x=alt.X("Estilo", sort="-y"),
        y="Barriles",
        color=alt.Color("Estilo", scale=alt.Scale(
            domain=list(colores.keys()),
            range=list(colores.values())
        )),
        tooltip=["Estilo", "Barriles"]
    ).properties(width=600, height=400)

    st.altair_chart(chart, use_container_width=True)

else:
    st.error("No se cargaron datos.")
