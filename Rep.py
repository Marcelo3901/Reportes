from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import requests
import streamlit as st


# -----------------------------------------------------------------------------
# CONFIGURACION GENERAL
# -----------------------------------------------------------------------------
SHEET_ID = "1FjQ8XBDwDdrlJZsNkQ6YyaygkHLhpKmfLBv6wd3uluY"
SHEET_BASE_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"

HOJA_BARRILES = "DatosM"
HOJA_MOVIMIENTOS_LATAS = "VLatas"
HOJA_INVENTARIO_LATAS = "InventarioLatasTR"

LITROS_POR_LATA = 0.330
ESTADOS_DESPACHO = {"despacho", "despachado"}
ESTADO_CUARTO_FRIO = "en cuarto frio"

COLOR_PRIMARIO = "#20CB80"
COLOR_DORADO = "#F2C14E"
COLOR_BARRIL = "#8B5E3C"
COLOR_LATA = "#20CB80"
COLOR_ALERTA = "#E45756"
COLOR_OK = "#2A9D8F"
UMBRAL_ALERTA_PREDETERMINADO = 200.0

COLORES_PRESENTACION = {
    "Barril": COLOR_BARRIL,
    "Lata": COLOR_LATA,
}

COLORES_ESTILOS = {
    "Golden": "#E4BE24",
    "IPA": "#18A66A",
    "Barley Wine": "#6A3D9A",
    "Session IPA": "#5BCB5A",
    "Trigo": "#D9A90D",
    "Vienna Lager": "#E8751A",
    "Vienna": "#E8751A",
    "Stout": "#3F3E3D",
    "Otros": "#A9A6A3",
    "Amber": "#E84A3A",
    "Maracuy\u00e1": "#D6C900",
    "Maracuya": "#D6C900",
    "Brown Ale Cafe": "#5A7A35",
    "Brown Ale Caf\u00e9": "#5A7A35",
    "Catharina Sour": "#E76F92",
    "Gose": "#5EAAA8",
    "Imperial IPA": "#2E8B57",
    "NEIPA": "#80B918",
    "Imperial Stout": "#1F1F1F",
    "Sin definir": "#9AA5A8",
}

PALETA_SUPLENTE = [
    "#277DA1",
    "#F9844A",
    "#43AA8B",
    "#F94144",
    "#577590",
    "#90BE6D",
    "#F8961E",
    "#9B5DE5",
    "#00BBF9",
    "#F15BB5",
    "#6D597A",
    "#457B9D",
]

ORDEN_DIAS = [
    "Lunes",
    "Martes",
    "Mi\u00e9rcoles",
    "Jueves",
    "Viernes",
    "S\u00e1bado",
    "Domingo",
]


# -----------------------------------------------------------------------------
# FUNCIONES DE LIMPIEZA Y LECTURA
# -----------------------------------------------------------------------------
def normalizar_clave(valor: object) -> str:
    """Normaliza texto para comparaciones: minusculas, sin tildes y sin espacios dobles."""
    if valor is None or pd.isna(valor):
        return ""
    texto = str(valor).strip().lower()
    texto = " ".join(texto.split())
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def limpiar_texto(serie: pd.Series, valor_vacio: str = "") -> pd.Series:
    resultado = serie.astype("string").fillna("").str.strip()
    resultado = resultado.str.replace(r"\s+", " ", regex=True)
    resultado = resultado.mask(
        resultado.str.lower().isin({"nan", "none", "nat", "<na>"}), ""
    )
    if valor_vacio:
        resultado = resultado.mask(resultado.eq(""), valor_vacio)
    return resultado


def columnas_relacionadas(df: pd.DataFrame, nombre_base: str) -> list[str]:
    """Encuentra columnas duplicadas por pandas, por ejemplo Estado, Estado.1, Estado.2."""
    base = normalizar_clave(nombre_base)
    encontradas: list[str] = []
    for columna in df.columns:
        normalizada = normalizar_clave(columna)
        if normalizada == base or normalizada.startswith(f"{base}."):
            encontradas.append(columna)
    return encontradas


def combinar_columnas(df: pd.DataFrame, nombre_base: str) -> pd.Series:
    """Devuelve el primer valor no vacio entre columnas equivalentes."""
    columnas = columnas_relacionadas(df, nombre_base)
    if not columnas:
        return pd.Series("", index=df.index, dtype="string")

    resultado = pd.Series(pd.NA, index=df.index, dtype="string")
    for columna in columnas:
        valores = limpiar_texto(df[columna])
        valores = valores.mask(valores.eq(""), pd.NA)
        resultado = resultado.fillna(valores)

    return resultado.fillna("").astype("string")


def convertir_fechas(serie: pd.Series) -> pd.Series:
    """Convierte fechas de Sheets, incluyendo seriales numericos de Google/Excel."""
    texto = limpiar_texto(serie)
    numeros = pd.to_numeric(texto, errors="coerce")

    resultado = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")
    es_serial = numeros.between(20000, 70000, inclusive="both").fillna(False)

    if es_serial.any():
        resultado.loc[es_serial] = pd.to_datetime(
            numeros.loc[es_serial], unit="D", origin="1899-12-30", errors="coerce"
        )

    restantes = ~es_serial
    if restantes.any():
        resultado.loc[restantes] = pd.to_datetime(
            texto.loc[restantes], dayfirst=True, errors="coerce"
        )

        # Respaldo para posibles fechas con mes primero.
        faltantes = restantes & resultado.isna() & texto.ne("")
        if faltantes.any():
            resultado.loc[faltantes] = pd.to_datetime(
                texto.loc[faltantes], dayfirst=False, errors="coerce"
            )

    return resultado


def convertir_cantidades(serie: pd.Series) -> pd.Series:
    """Convierte cantidades enteras y reconoce 1.200 como 1200."""
    texto = limpiar_texto(serie).str.replace(" ", "", regex=False)

    # Formato colombiano/espanol de miles: 1.200, 12.500, etc.
    miles_punto = texto.str.match(r"^-?\d{1,3}(?:\.\d{3})+$", na=False)
    texto = texto.where(~miles_punto, texto.str.replace(".", "", regex=False))

    # Si quedan comas, se interpretan como separador decimal.
    texto = texto.str.replace(",", ".", regex=False)
    return pd.to_numeric(texto, errors="coerce")


def limpiar_codigo(serie: pd.Series) -> pd.Series:
    codigo = limpiar_texto(serie)
    codigo = codigo.str.replace(r"\.0$", "", regex=True)
    codigo = codigo.str.replace(r"[^0-9]", "", regex=True)
    return codigo


def limpiar_lote(serie: pd.Series) -> pd.Series:
    lote = limpiar_texto(serie)
    lote = lote.str.replace(r"\.0$", "", regex=True)
    return lote.mask(lote.str.lower().eq("nan"), "")


def extraer_decimal(serie: pd.Series) -> pd.Series:
    texto = limpiar_texto(serie).str.replace(",", ".", regex=False)
    numero = texto.str.extract(r"(-?\d+(?:\.\d+)?)", expand=False)
    return pd.to_numeric(numero, errors="coerce")


def litros_mencionados_en_observacion(serie: pd.Series) -> pd.Series:
    texto = limpiar_texto(serie).str.replace(",", ".", regex=False)
    numero = texto.str.extract(
        r"(?i)(\d+(?:\.\d+)?)\s*(?:l|lt|lts|litro|litros)\b",
        expand=False,
    )
    return pd.to_numeric(numero, errors="coerce")


def capacidad_nominal_por_codigo(codigos: pd.Series) -> pd.Series:
    prefijos = codigos.astype("string").str[:2]
    return prefijos.map({"20": 20.0, "30": 30.0, "58": 58.0}).fillna(0.0)


def calcular_litros_barril(
    codigos: pd.Series,
    capacidades: pd.Series,
    observaciones: pd.Series,
) -> pd.Series:
    """
    Prioridad para calcular litros:
    1. Litros indicados en observaciones (ej. "Barril con 14 lt").
    2. Columna Capacidad, si contiene un valor valido.
    3. Prefijo del codigo: 20, 30 o 58 litros.
    """
    litros_observacion = litros_mencionados_en_observacion(observaciones)
    litros_capacidad = extraer_decimal(capacidades)
    litros_capacidad = litros_capacidad.where(litros_capacidad.between(1, 100))
    litros_codigo = capacidad_nominal_por_codigo(codigos)

    litros = litros_observacion.copy()
    litros = litros.where(litros.notna(), litros_capacidad)
    litros = litros.where(litros.notna(), litros_codigo.where(litros_codigo.ne(0)))
    return pd.to_numeric(litros, errors="coerce").fillna(0.0)


@st.cache_data(ttl=120, show_spinner=False)
def leer_hoja(nombre_hoja: str) -> pd.DataFrame:
    """Lee una pestaña publica de Google Sheets como CSV."""
    nombre_codificado = quote(nombre_hoja, safe="")
    url = f"{SHEET_BASE_URL}/gviz/tq?tqx=out:csv&sheet={nombre_codificado}"

    respuesta = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    respuesta.raise_for_status()
    respuesta.encoding = "utf-8"

    contenido = respuesta.text.lstrip()
    if contenido.lower().startswith("<!doctype html") or contenido.lower().startswith("<html"):
        raise RuntimeError(
            f"Google Sheets no devolvio un CSV para la hoja '{nombre_hoja}'. "
            "Verifica que el archivo sea accesible desde la aplicacion."
        )

    df = pd.read_csv(
        io.StringIO(respuesta.text),
        dtype=str,
        keep_default_na=False,
    )
    df.columns = [str(columna).strip() for columna in df.columns]
    return df


def cargar_hoja_segura(nombre_hoja: str) -> tuple[pd.DataFrame, str | None]:
    try:
        return leer_hoja(nombre_hoja), None
    except Exception as exc:  # La app puede continuar mostrando las otras fuentes.
        return pd.DataFrame(), str(exc)


# -----------------------------------------------------------------------------
# PREPARACION DE DATOS
# -----------------------------------------------------------------------------
def preparar_barriles(df_origen: pd.DataFrame) -> pd.DataFrame:
    columnas_salida = [
        "Fecha",
        "Codigo",
        "Lote",
        "Estilo",
        "Estado",
        "Estado_normalizado",
        "Cliente",
        "Responsable",
        "Observaciones",
        "Litros",
    ]
    if df_origen.empty:
        return pd.DataFrame(columns=columnas_salida)

    codigo = limpiar_codigo(combinar_columnas(df_origen, "Codigo"))
    observaciones = limpiar_texto(combinar_columnas(df_origen, "Observaciones"))
    capacidad = combinar_columnas(df_origen, "Capacidad")
    estado = limpiar_texto(combinar_columnas(df_origen, "Estado"))

    df = pd.DataFrame(
        {
            "Fecha": convertir_fechas(combinar_columnas(df_origen, "Marca temporal")),
            "Codigo": codigo,
            "Lote": limpiar_lote(combinar_columnas(df_origen, "Lote")),
            "Estilo": limpiar_texto(
                combinar_columnas(df_origen, "Estilo"), valor_vacio="Sin definir"
            ),
            "Estado": estado,
            "Cliente": limpiar_texto(
                combinar_columnas(df_origen, "Cliente"), valor_vacio="Sin definir"
            ),
            "Responsable": limpiar_texto(
                combinar_columnas(df_origen, "Responsable"), valor_vacio="Sin definir"
            ),
            "Observaciones": observaciones,
        }
    )

    df["Estado_normalizado"] = df["Estado"].map(normalizar_clave)
    df["Litros"] = calcular_litros_barril(codigo, capacidad, observaciones)
    df = df[df["Fecha"].notna() & df["Codigo"].ne("")].copy()
    return df[columnas_salida]


def preparar_movimientos_latas(df_origen: pd.DataFrame) -> pd.DataFrame:
    columnas_salida = [
        "Fecha",
        "Estilo",
        "Cantidad",
        "Lote",
        "Cliente",
        "Responsable",
        "Estado",
        "Estado_normalizado",
        "Litros",
    ]
    if df_origen.empty:
        return pd.DataFrame(columns=columnas_salida)

    estado = limpiar_texto(combinar_columnas(df_origen, "Estado"))
    cantidad = convertir_cantidades(combinar_columnas(df_origen, "Cantidad"))

    df = pd.DataFrame(
        {
            "Fecha": convertir_fechas(combinar_columnas(df_origen, "Marca temporal")),
            "Estilo": limpiar_texto(
                combinar_columnas(df_origen, "Estilo"), valor_vacio="Sin definir"
            ),
            "Cantidad": cantidad,
            "Lote": limpiar_lote(combinar_columnas(df_origen, "Lote")),
            "Cliente": limpiar_texto(
                combinar_columnas(df_origen, "Cliente"), valor_vacio="Sin definir"
            ),
            "Responsable": limpiar_texto(
                combinar_columnas(df_origen, "Responsable"), valor_vacio="Sin definir"
            ),
            "Estado": estado,
        }
    )

    df["Estado_normalizado"] = df["Estado"].map(normalizar_clave)
    df["Litros"] = df["Cantidad"].fillna(0) * LITROS_POR_LATA
    df = df[
        df["Fecha"].notna()
        & df["Cantidad"].notna()
        & df["Cantidad"].gt(0)
    ].copy()
    return df[columnas_salida]


def preparar_inventario_latas(df_origen: pd.DataFrame) -> pd.DataFrame:
    columnas_salida = [
        "Estilo",
        "Lote",
        "Ingresadas",
        "Despachadas",
        "Devoluciones",
        "Bajas",
        "Disponible",
        "Litros",
    ]
    if df_origen.empty:
        return pd.DataFrame(columns=columnas_salida)

    ingresadas = convertir_cantidades(combinar_columnas(df_origen, "Ingresadas")).fillna(0)
    despachadas = convertir_cantidades(combinar_columnas(df_origen, "Despachadas")).fillna(0)
    devoluciones = convertir_cantidades(combinar_columnas(df_origen, "Devoluciones")).fillna(0)
    bajas = convertir_cantidades(combinar_columnas(df_origen, "Bajas")).fillna(0)
    disponible = convertir_cantidades(combinar_columnas(df_origen, "Disponible"))

    # Respaldo en caso de que la columna Disponible no exista o este vacia.
    disponible_calculado = ingresadas - despachadas + devoluciones - bajas
    disponible = disponible.fillna(disponible_calculado)

    df = pd.DataFrame(
        {
            "Estilo": limpiar_texto(
                combinar_columnas(df_origen, "Estilo"), valor_vacio="Sin definir"
            ),
            "Lote": limpiar_lote(combinar_columnas(df_origen, "Lote")),
            "Ingresadas": ingresadas,
            "Despachadas": despachadas,
            "Devoluciones": devoluciones,
            "Bajas": bajas,
            "Disponible": disponible,
        }
    )
    df["Litros"] = df["Disponible"].fillna(0) * LITROS_POR_LATA
    df = df[df["Disponible"].fillna(0).gt(0)].copy()
    return df[columnas_salida]


def obtener_inventario_barriles_actual(df_barriles: pd.DataFrame) -> pd.DataFrame:
    if df_barriles.empty:
        return df_barriles.copy()

    ultimos = (
        df_barriles.sort_values("Fecha", ascending=False)
        .drop_duplicates(subset="Codigo", keep="first")
        .copy()
    )
    return ultimos[ultimos["Estado_normalizado"].eq(ESTADO_CUARTO_FRIO)].copy()


def construir_despachos(
    df_barriles: pd.DataFrame,
    df_latas: pd.DataFrame,
) -> pd.DataFrame:
    columnas = [
        "Fecha",
        "Tipo",
        "Cliente",
        "Estilo",
        "Codigo",
        "Lote",
        "Barriles",
        "Latas",
        "Litros_barriles",
        "Litros_latas",
        "Litros_totales",
        "Responsable",
        "Observaciones",
    ]
    partes: list[pd.DataFrame] = []

    if not df_barriles.empty:
        barriles = df_barriles[
            df_barriles["Estado_normalizado"].isin(ESTADOS_DESPACHO)
        ].copy()
        if not barriles.empty:
            barriles["Tipo"] = "Barril"
            barriles["Barriles"] = 1
            barriles["Latas"] = 0.0
            barriles["Litros_barriles"] = barriles["Litros"]
            barriles["Litros_latas"] = 0.0
            barriles["Litros_totales"] = barriles["Litros"]
            partes.append(barriles[columnas])

    if not df_latas.empty:
        # Estado vacio se considera despacho historico, igual que en el inventario.
        es_despacho = (
            df_latas["Estado_normalizado"].isin(ESTADOS_DESPACHO)
            | df_latas["Estado_normalizado"].eq("")
        )
        latas = df_latas[es_despacho].copy()
        if not latas.empty:
            latas["Tipo"] = "Lata"
            latas["Codigo"] = ""
            latas["Barriles"] = 0
            latas["Latas"] = latas["Cantidad"]
            latas["Litros_barriles"] = 0.0
            latas["Litros_latas"] = latas["Litros"]
            latas["Litros_totales"] = latas["Litros"]
            latas["Observaciones"] = ""
            partes.append(latas[columnas])

    if not partes:
        return pd.DataFrame(columns=columnas)

    return pd.concat(partes, ignore_index=True).sort_values("Fecha")


# -----------------------------------------------------------------------------
# FORMATO Y COMPONENTES VISUALES
# -----------------------------------------------------------------------------
def aplicar_estilos_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --castiza-green: #20CB80;
            --castiza-gold: #F2C14E;
            --castiza-dark: #163C31;
            --castiza-text: #213238;
        }
        .stApp {
            background:
                radial-gradient(circle at 8% 0%, rgba(32,203,128,.13), transparent 28%),
                radial-gradient(circle at 96% 4%, rgba(242,193,78,.16), transparent 25%),
                linear-gradient(180deg, #F9FCFA 0%, #EDF5F1 100%);
            color: var(--castiza-text);
        }
        .block-container {
            max-width: 1550px;
            padding-top: 1.15rem;
            padding-bottom: 2.5rem;
        }
        .hero-castiza {
            background: linear-gradient(120deg, #163C31 0%, #1F6650 58%, #20A875 100%);
            border: 1px solid rgba(255,255,255,.18);
            border-radius: 24px;
            padding: 1.45rem 1.7rem;
            margin-bottom: 1.1rem;
            box-shadow: 0 16px 40px rgba(22,60,49,.18);
            color: white;
        }
        .hero-castiza h1 {
            margin: 0;
            color: white;
            font-size: clamp(1.7rem, 3vw, 2.7rem);
            letter-spacing: -.03em;
        }
        .hero-castiza p {
            margin: .5rem 0 0;
            color: rgba(255,255,255,.85);
            font-size: 1rem;
            max-width: 980px;
        }
        .hero-chip {
            display: inline-block;
            margin-top: .9rem;
            margin-right: .45rem;
            padding: .34rem .72rem;
            border-radius: 999px;
            background: rgba(255,255,255,.13);
            border: 1px solid rgba(255,255,255,.20);
            font-size: .82rem;
            font-weight: 700;
        }
        [data-testid="stMetric"] {
            background: linear-gradient(145deg, rgba(255,255,255,.98), rgba(245,251,248,.96));
            border: 1px solid rgba(32,203,128,.16);
            border-left: 5px solid var(--castiza-green);
            border-radius: 16px;
            padding: .85rem 1rem;
            box-shadow: 0 8px 22px rgba(33,50,56,.07);
            min-height: 112px;
        }
        [data-testid="stMetricLabel"] {
            color: #5C6C70;
            font-weight: 750;
        }
        [data-testid="stMetricValue"] {
            color: #163C31;
            font-weight: 850;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #163C31 0%, #1F5A48 100%);
        }
        [data-testid="stSidebar"] * {
            color: #F4FBF8;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            color: #213238 !important;
            background: white !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: .35rem;
            padding: .3rem;
            border-radius: 14px;
            background: rgba(255,255,255,.78);
            border: 1px solid rgba(32,203,128,.14);
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 10px;
            font-weight: 750;
            padding-left: .9rem;
            padding-right: .9rem;
        }
        .stTabs [aria-selected="true"] {
            color: #116B4A !important;
            background: rgba(32,203,128,.10) !important;
        }
        .stButton > button,
        .stDownloadButton > button {
            border-radius: 12px;
            border: 1px solid rgba(32,203,128,.34);
            font-weight: 750;
            transition: all .18s ease;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--castiza-green);
            color: #126B4B;
            transform: translateY(-1px);
            box-shadow: 0 6px 14px rgba(32,203,128,.16);
        }
        [data-testid="stDataFrame"],
        [data-testid="stTable"] {
            border: 1px solid rgba(33,50,56,.09);
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 8px 22px rgba(33,50,56,.05);
        }
        .section-note {
            background: white;
            border: 1px solid rgba(32,203,128,.17);
            border-left: 5px solid var(--castiza-gold);
            border-radius: 14px;
            padding: .85rem 1rem;
            margin: .3rem 0 1rem;
            color: #415257;
        }
        h2, h3, h4 { color: #173F33; }
        hr { border-color: rgba(33,50,56,.10); }
        </style>
        """,
        unsafe_allow_html=True,
    )


def mostrar_encabezado() -> None:
    st.markdown(
        """
        <div class="hero-castiza">
            <h1>&#127866; Reporte de barriles y latas</h1>
            <p>
                Inventario, despachos y litros equivalentes en un solo panel. Los datos se
                leen directamente de Google Sheets y cada lata se convierte a 0,330 litros.
            </p>
            <span class="hero-chip">Inventario en tiempo real</span>
            <span class="hero-chip">Barriles + latas</span>
            <span class="hero-chip">Gr&aacute;ficos interactivos</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hoy_bogota() -> date:
    try:
        return datetime.now(ZoneInfo("America/Bogota")).date()
    except Exception:
        return datetime.now().date()


def formato_numero(valor: float, decimales: int = 0) -> str:
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def normalizar_tipos_resumen(df: pd.DataFrame) -> pd.DataFrame:
    resultado = df.copy()
    for columna in ["Barriles", "Latas", "Movimientos"]:
        if columna in resultado.columns:
            resultado[columna] = resultado[columna].fillna(0).round().astype(int)
    for columna in ["Litros barriles", "Litros latas", "Litros totales", "Litros"]:
        if columna in resultado.columns:
            resultado[columna] = resultado[columna].fillna(0).round(2)
    return resultado


def escala_estilos(valores: list[str] | pd.Series) -> alt.Scale:
    estilos = list(dict.fromkeys(str(valor) for valor in list(valores) if str(valor).strip()))
    colores = [
        COLORES_ESTILOS.get(estilo, PALETA_SUPLENTE[i % len(PALETA_SUPLENTE)])
        for i, estilo in enumerate(estilos)
    ]
    return alt.Scale(domain=estilos, range=colores)


def escala_presentacion() -> alt.Scale:
    return alt.Scale(
        domain=list(COLORES_PRESENTACION.keys()),
        range=list(COLORES_PRESENTACION.values()),
    )


def estilizar_grafico(grafico: alt.TopLevelMixin) -> alt.TopLevelMixin:
    return (
        grafico.configure_view(strokeOpacity=0)
        .configure_axis(
            labelColor="#43565B",
            titleColor="#263B40",
            gridColor="#DFE9E5",
            gridOpacity=.65,
            labelFontSize=11,
            titleFontSize=12,
        )
        .configure_legend(
            labelColor="#43565B",
            titleColor="#263B40",
            orient="bottom",
            direction="horizontal",
        )
        .configure_title(
            color="#173F33",
            fontSize=17,
            fontWeight=700,
            anchor="start",
            offset=14,
        )
    )


def mostrar_grafico(grafico: alt.TopLevelMixin | None) -> None:
    if grafico is None:
        st.info("No hay datos suficientes para generar este gr\u00e1fico.")
        return
    st.altair_chart(estilizar_grafico(grafico), use_container_width=True)


def mostrar_metricas(
    barriles: float,
    latas: float,
    litros_barriles: float,
    litros_latas: float,
    movimientos: float | None = None,
) -> None:
    litros_totales = litros_barriles + litros_latas
    columnas = st.columns(6 if movimientos is not None else 5)
    columnas[0].metric("\U0001F6E2\uFE0F Barriles", formato_numero(barriles, 0))
    columnas[1].metric("\U0001F96B Latas", formato_numero(latas, 0))
    columnas[2].metric("\U0001F37A Litros en barriles", f"{formato_numero(litros_barriles, 1)} L")
    columnas[3].metric("\U0001F4A7 Litros en latas", f"{formato_numero(litros_latas, 2)} L")
    columnas[4].metric("\U0001F4E6 Litros totales", f"{formato_numero(litros_totales, 2)} L")
    if movimientos is not None:
        columnas[5].metric("\U0001F9FE Movimientos", formato_numero(movimientos, 0))


def crear_grafico_dona(
    df: pd.DataFrame,
    categoria: str,
    valor: str,
    titulo: str,
    modo_color: str = "estilo",
    sufijo: str = " L",
) -> alt.TopLevelMixin | None:
    if df.empty:
        return None

    agrupado = (
        df.groupby(categoria, as_index=False)[valor]
        .sum()
        .sort_values(valor, ascending=False)
    )
    agrupado = agrupado[agrupado[valor].gt(0)].copy()
    if agrupado.empty:
        return None

    total = float(agrupado[valor].sum())
    agrupado["Participacion"] = agrupado[valor] / total if total else 0

    if modo_color == "presentacion":
        escala = escala_presentacion()
    else:
        escala = escala_estilos(agrupado[categoria].tolist())

    arcos = (
        alt.Chart(agrupado)
        .mark_arc(innerRadius=70, outerRadius=118, stroke="white", strokeWidth=2)
        .encode(
            theta=alt.Theta(f"{valor}:Q", stack=True),
            color=alt.Color(
                f"{categoria}:N",
                scale=escala,
                title=categoria,
                sort=agrupado[categoria].tolist(),
            ),
            tooltip=[
                alt.Tooltip(f"{categoria}:N", title=categoria),
                alt.Tooltip(f"{valor}:Q", title=valor, format=",.2f"),
                alt.Tooltip("Participacion:Q", title="Participaci\u00f3n", format=".1%"),
            ],
        )
    )
    centro = (
        alt.Chart(pd.DataFrame({"Texto": [f"{formato_numero(total, 1)}{sufijo}"]}))
        .mark_text(fontSize=21, fontWeight="bold", color="#173F33")
        .encode(text="Texto:N")
    )
    return (arcos + centro).properties(title=titulo, height=335)


def grafico_litros_por_categoria(
    df: pd.DataFrame,
    categoria: str,
    titulo: str,
    top_n: int | None = None,
) -> alt.TopLevelMixin | None:
    if df.empty:
        return None

    datos = df.copy()
    if top_n:
        principales = datos.groupby(categoria)["Litros_totales"].sum().nlargest(top_n).index
        datos = datos[datos[categoria].isin(principales)]

    agrupado = (
        datos.groupby([categoria, "Tipo"], as_index=False)["Litros_totales"]
        .sum()
        .rename(columns={"Litros_totales": "Litros"})
    )
    if agrupado.empty:
        return None

    return (
        alt.Chart(agrupado)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            y=alt.Y(f"{categoria}:N", sort="-x", title=None),
            x=alt.X("Litros:Q", title="Litros"),
            color=alt.Color("Tipo:N", title="Presentaci\u00f3n", scale=escala_presentacion()),
            order=alt.Order("Tipo:N", sort="ascending"),
            tooltip=[
                alt.Tooltip(f"{categoria}:N", title=categoria),
                alt.Tooltip("Tipo:N", title="Presentaci\u00f3n"),
                alt.Tooltip("Litros:Q", title="Litros", format=",.2f"),
            ],
        )
        .properties(
            title=titulo,
            height=max(330, len(agrupado[categoria].unique()) * 28),
        )
    )


def aplicar_filtros_despachos(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, date, date, int]:
    if df.empty:
        hoy = hoy_bogota()
        return df, hoy, hoy, 10

    minimo = df["Fecha"].min().date()
    maximo = df["Fecha"].max().date()
    hoy = hoy_bogota()

    st.sidebar.markdown("---")
    st.sidebar.subheader("\U0001F50E Filtros de despachos")
    periodo = st.sidebar.selectbox(
        "Periodo",
        ["Mes actual", "A\u00f1o actual", "Todo el historial", "Rango personalizado"],
        key="periodo_despachos",
    )

    if periodo == "Mes actual":
        fecha_inicio = date(hoy.year, hoy.month, 1)
        fecha_fin = hoy
    elif periodo == "A\u00f1o actual":
        fecha_inicio = date(hoy.year, 1, 1)
        fecha_fin = hoy
    elif periodo == "Todo el historial":
        fecha_inicio = minimo
        fecha_fin = maximo
    else:
        fecha_inicio = st.sidebar.date_input(
            "Fecha inicial",
            value=max(minimo, date(hoy.year, hoy.month, 1)),
            min_value=minimo,
            max_value=maximo,
            key="fecha_inicio_despachos",
        )
        fecha_fin = st.sidebar.date_input(
            "Fecha final",
            value=min(hoy, maximo),
            min_value=minimo,
            max_value=maximo,
            key="fecha_fin_despachos",
        )

    if fecha_inicio > fecha_fin:
        fecha_inicio, fecha_fin = fecha_fin, fecha_inicio

    clientes = sorted(df["Cliente"].dropna().astype(str).unique().tolist())
    estilos = sorted(df["Estilo"].dropna().astype(str).unique().tolist())

    clientes_seleccionados = st.sidebar.multiselect(
        "Clientes (vac\u00edo = todos)",
        clientes,
        key="clientes_despachos",
    )
    estilos_seleccionados = st.sidebar.multiselect(
        "Estilos (vac\u00edo = todos)",
        estilos,
        key="estilos_despachos",
    )
    presentacion = st.sidebar.selectbox(
        "Presentaci\u00f3n",
        ["Todas", "Barril", "Lata"],
        key="presentacion_despachos",
    )
    top_n = st.sidebar.slider(
        "Elementos en rankings",
        min_value=5,
        max_value=25,
        value=10,
        step=1,
        key="top_n_despachos",
    )

    filtrado = df[df["Fecha"].dt.date.between(fecha_inicio, fecha_fin, inclusive="both")].copy()
    if clientes_seleccionados:
        filtrado = filtrado[filtrado["Cliente"].isin(clientes_seleccionados)]
    if estilos_seleccionados:
        filtrado = filtrado[filtrado["Estilo"].isin(estilos_seleccionados)]
    if presentacion != "Todas":
        filtrado = filtrado[filtrado["Tipo"].eq(presentacion)]

    return filtrado, fecha_inicio, fecha_fin, top_n


# -----------------------------------------------------------------------------
# GRAFICOS Y VISTA DE INVENTARIO
# -----------------------------------------------------------------------------
def construir_resumen_inventario(
    inventario_barriles: pd.DataFrame,
    inventario_latas: pd.DataFrame,
    umbral_alerta: float,
) -> pd.DataFrame:
    if inventario_barriles.empty:
        resumen_barriles = pd.DataFrame(columns=["Estilo", "Barriles", "Litros barriles"])
    else:
        resumen_barriles = (
            inventario_barriles.groupby("Estilo", as_index=False)
            .agg(Barriles=("Codigo", "count"), **{"Litros barriles": ("Litros", "sum")})
        )

    if inventario_latas.empty:
        resumen_latas = pd.DataFrame(columns=["Estilo", "Latas", "Litros latas"])
    else:
        resumen_latas = (
            inventario_latas.groupby("Estilo", as_index=False)
            .agg(Latas=("Disponible", "sum"), **{"Litros latas": ("Litros", "sum")})
        )

    resumen = pd.merge(resumen_barriles, resumen_latas, on="Estilo", how="outer").fillna(0)
    if resumen.empty:
        return resumen

    resumen["Litros totales"] = resumen["Litros barriles"] + resumen["Litros latas"]
    resumen["Estado inventario"] = resumen["Litros totales"].apply(
        lambda valor: "\u26A0\uFE0F Bajo" if valor < umbral_alerta else "\u2705 Adecuado"
    )
    resumen = normalizar_tipos_resumen(resumen)
    return resumen.sort_values("Litros totales", ascending=False)


def grafico_inventario_apilado(resumen: pd.DataFrame) -> alt.TopLevelMixin | None:
    if resumen.empty:
        return None
    datos = resumen.melt(
        id_vars="Estilo",
        value_vars=["Litros barriles", "Litros latas"],
        var_name="Presentacion",
        value_name="Litros",
    )
    datos["Presentacion"] = datos["Presentacion"].replace(
        {"Litros barriles": "Barril", "Litros latas": "Lata"}
    )
    return (
        alt.Chart(datos)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            y=alt.Y("Estilo:N", sort="-x", title=None),
            x=alt.X("Litros:Q", title="Litros disponibles"),
            color=alt.Color("Presentacion:N", title="Presentaci\u00f3n", scale=escala_presentacion()),
            tooltip=["Estilo", "Presentacion", alt.Tooltip("Litros:Q", format=",.2f")],
        )
        .properties(
            title="Litros disponibles por estilo y presentaci\u00f3n",
            height=max(340, len(resumen) * 29),
        )
    )


def grafico_estado_inventario(
    resumen: pd.DataFrame,
    umbral: float,
) -> alt.TopLevelMixin | None:
    if resumen.empty:
        return None

    datos = resumen.copy()
    datos["Nivel"] = datos["Litros totales"].apply(
        lambda valor: "Bajo" if valor < umbral else "Adecuado"
    )
    barras = (
        alt.Chart(datos)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            y=alt.Y("Estilo:N", sort="-x", title=None),
            x=alt.X("Litros totales:Q", title="Litros totales"),
            color=alt.Color(
                "Nivel:N",
                scale=alt.Scale(domain=["Bajo", "Adecuado"], range=[COLOR_ALERTA, COLOR_OK]),
                title="Nivel",
            ),
            tooltip=["Estilo", "Nivel", alt.Tooltip("Litros totales:Q", format=",.2f")],
        )
    )
    regla = (
        alt.Chart(pd.DataFrame({"Umbral": [umbral]}))
        .mark_rule(color=COLOR_ALERTA, strokeDash=[5, 4], strokeWidth=2)
        .encode(x="Umbral:Q")
    )
    return (barras + regla).properties(
        title=f"Sem\u00e1foro de inventario · alerta por debajo de {formato_numero(umbral, 0)} L",
        height=max(340, len(resumen) * 29),
    )


def grafico_mezcla_inventario(resumen: pd.DataFrame) -> alt.TopLevelMixin | None:
    if resumen.empty:
        return None
    return (
        alt.Chart(resumen)
        .mark_circle(opacity=.86, stroke="white", strokeWidth=1.5)
        .encode(
            x=alt.X("Litros barriles:Q", title="Litros en barriles"),
            y=alt.Y("Litros latas:Q", title="Litros en latas"),
            size=alt.Size("Litros totales:Q", title="Litros totales", scale=alt.Scale(range=[120, 1800])),
            color=alt.Color("Estilo:N", scale=escala_estilos(resumen["Estilo"].tolist()), title="Estilo"),
            tooltip=[
                "Estilo",
                alt.Tooltip("Barriles:Q", format=",.0f"),
                alt.Tooltip("Latas:Q", format=",.0f"),
                alt.Tooltip("Litros barriles:Q", format=",.2f"),
                alt.Tooltip("Litros latas:Q", format=",.2f"),
                alt.Tooltip("Litros totales:Q", format=",.2f"),
            ],
        )
        .properties(title="Mezcla de inventario: barriles vs. latas", height=390)
    )


def grafico_lotes_latas(
    inventario_latas: pd.DataFrame,
    top_n: int = 25,
) -> alt.TopLevelMixin | None:
    if inventario_latas.empty:
        return None
    datos = inventario_latas.copy()
    datos["Etiqueta"] = datos["Estilo"] + " · " + datos["Lote"].replace("", "Sin lote")
    datos = datos.nlargest(top_n, "Litros")
    return (
        alt.Chart(datos)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            y=alt.Y("Etiqueta:N", sort="-x", title=None),
            x=alt.X("Disponible:Q", title="Latas disponibles"),
            color=alt.Color("Estilo:N", scale=escala_estilos(datos["Estilo"].tolist()), title="Estilo"),
            tooltip=[
                "Estilo",
                "Lote",
                alt.Tooltip("Disponible:Q", format=",.0f"),
                alt.Tooltip("Litros:Q", format=",.2f"),
            ],
        )
        .properties(
            title=f"Lotes de latas con mayor disponibilidad · Top {top_n}",
            height=max(380, len(datos) * 25),
        )
    )


def grafico_capacidad_barriles(
    inventario_barriles: pd.DataFrame,
) -> alt.TopLevelMixin | None:
    if inventario_barriles.empty:
        return None
    datos = inventario_barriles.copy()
    datos["Capacidad nominal"] = capacidad_nominal_por_codigo(datos["Codigo"])
    datos["Capacidad"] = datos["Capacidad nominal"].apply(
        lambda valor: f"{int(valor)} L" if valor > 0 else "Otra"
    )
    agrupado = (
        datos.groupby(["Estilo", "Capacidad"], as_index=False)
        .agg(Barriles=("Codigo", "count"))
    )
    return (
        alt.Chart(agrupado)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("Estilo:N", sort="-y", title=None),
            y=alt.Y("Barriles:Q", title="N\u00famero de barriles"),
            color=alt.Color("Capacidad:N", title="Capacidad nominal"),
            tooltip=["Estilo", "Capacidad", "Barriles"],
        )
        .properties(title="Barriles por estilo y capacidad nominal", height=390)
    )


def mostrar_inventario_actual(
    inventario_barriles: pd.DataFrame,
    inventario_latas: pd.DataFrame,
    umbral_alerta: float,
) -> None:
    st.subheader("\U0001F4E6 Inventario actual en cuarto fr\u00edo")
    st.markdown(
        f"""
        <div class="section-note">
        El inventario combina el \u00faltimo estado de cada barril con el saldo autom\u00e1tico de
        <b>InventarioLatasTR</b>. Cada lata equivale a <b>{LITROS_POR_LATA:.3f} litros</b>.
        El sem\u00e1foro considera inventario bajo cuando un estilo tiene menos de
        <b>{formato_numero(umbral_alerta, 0)} litros</b> combinados.
        </div>
        """,
        unsafe_allow_html=True,
    )

    total_barriles = float(len(inventario_barriles))
    total_latas = float(inventario_latas["Disponible"].sum()) if not inventario_latas.empty else 0.0
    litros_barriles = float(inventario_barriles["Litros"].sum()) if not inventario_barriles.empty else 0.0
    litros_latas = float(inventario_latas["Litros"].sum()) if not inventario_latas.empty else 0.0
    mostrar_metricas(total_barriles, total_latas, litros_barriles, litros_latas)

    resumen = construir_resumen_inventario(inventario_barriles, inventario_latas, umbral_alerta)
    if resumen.empty:
        st.warning("No se encontraron existencias actuales.")
        return

    estilos_bajos = int(resumen["Estado inventario"].str.contains("Bajo").sum())
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("\U0001F3A8 Estilos con inventario", formato_numero(len(resumen), 0))
    col_b.metric("\u26A0\uFE0F Estilos bajo el umbral", formato_numero(estilos_bajos, 0))
    col_c.metric(
        "\U0001F4CA Promedio por estilo",
        f"{formato_numero(resumen['Litros totales'].mean(), 2)} L",
    )

    tab_resumen, tab_visual, tab_alertas, tab_detalle = st.tabs(
        ["Resumen", "An\u00e1lisis visual", "Alertas y lotes", "Detalle"]
    )

    with tab_resumen:
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        mostrar_grafico(grafico_inventario_apilado(resumen))

        presentaciones = pd.DataFrame(
            {
                "Tipo": ["Barril", "Lata"],
                "Litros": [litros_barriles, litros_latas],
            }
        )
        col_1, col_2 = st.columns(2)
        with col_1:
            mostrar_grafico(
                crear_grafico_dona(
                    resumen,
                    categoria="Estilo",
                    valor="Litros totales",
                    titulo="Distribuci\u00f3n del inventario por estilo",
                )
            )
        with col_2:
            mostrar_grafico(
                crear_grafico_dona(
                    presentaciones,
                    categoria="Tipo",
                    valor="Litros",
                    titulo="Inventario por presentaci\u00f3n",
                    modo_color="presentacion",
                )
            )

    with tab_visual:
        col_1, col_2 = st.columns(2)
        with col_1:
            mostrar_grafico(grafico_mezcla_inventario(resumen))
        with col_2:
            mostrar_grafico(grafico_capacidad_barriles(inventario_barriles))

    with tab_alertas:
        bajos = resumen[resumen["Estado inventario"].str.contains("Bajo")].copy()
        if bajos.empty:
            st.success("Todos los estilos se encuentran por encima del umbral configurado.")
        else:
            st.warning(
                "Estilos con inventario bajo: "
                + ", ".join(bajos["Estilo"].astype(str).tolist())
            )
            st.dataframe(
                bajos[["Estilo", "Barriles", "Latas", "Litros totales", "Estado inventario"]],
                use_container_width=True,
                hide_index=True,
            )
        mostrar_grafico(grafico_estado_inventario(resumen, umbral_alerta))
        mostrar_grafico(grafico_lotes_latas(inventario_latas))

    with tab_detalle:
        columna_barriles, columna_latas = st.columns(2)
        with columna_barriles:
            st.markdown("#### Barriles en cuarto fr\u00edo")
            if inventario_barriles.empty:
                st.info("No hay barriles registrados en cuarto fr\u00edo.")
            else:
                detalle = inventario_barriles[
                    ["Codigo", "Estilo", "Lote", "Litros", "Fecha", "Observaciones"]
                ].copy()
                detalle["Fecha"] = detalle["Fecha"].dt.strftime("%d/%m/%Y %H:%M")
                detalle["Litros"] = detalle["Litros"].round(2)
                st.dataframe(
                    detalle.sort_values(["Estilo", "Codigo"]),
                    use_container_width=True,
                    hide_index=True,
                )

        with columna_latas:
            st.markdown("#### Latas disponibles")
            if inventario_latas.empty:
                st.info("No hay latas disponibles.")
            else:
                detalle = inventario_latas[
                    [
                        "Estilo",
                        "Lote",
                        "Ingresadas",
                        "Despachadas",
                        "Devoluciones",
                        "Bajas",
                        "Disponible",
                        "Litros",
                    ]
                ].copy()
                for columna in ["Ingresadas", "Despachadas", "Devoluciones", "Bajas", "Disponible"]:
                    detalle[columna] = detalle[columna].round().astype(int)
                detalle["Litros"] = detalle["Litros"].round(2)
                st.dataframe(
                    detalle.sort_values(["Estilo", "Lote"]),
                    use_container_width=True,
                    hide_index=True,
                )


# -----------------------------------------------------------------------------
# GRAFICOS Y VISTA DE DESPACHOS
# -----------------------------------------------------------------------------
def grafico_pareto_clientes(
    df: pd.DataFrame,
    top_n: int,
) -> alt.TopLevelMixin | None:
    if df.empty:
        return None
    datos = (
        df.groupby("Cliente", as_index=False)["Litros_totales"]
        .sum()
        .rename(columns={"Litros_totales": "Litros"})
        .nlargest(top_n, "Litros")
        .sort_values("Litros", ascending=False)
    )
    if datos.empty:
        return None
    total = float(datos["Litros"].sum())
    datos["Acumulado"] = datos["Litros"].cumsum() / total if total else 0
    orden = datos["Cliente"].tolist()

    barras = (
        alt.Chart(datos)
        .mark_bar(color=COLOR_PRIMARIO, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("Cliente:N", sort=orden, axis=alt.Axis(labelAngle=-35), title=None),
            y=alt.Y("Litros:Q", title="Litros"),
            tooltip=["Cliente", alt.Tooltip("Litros:Q", format=",.2f")],
        )
    )
    linea = (
        alt.Chart(datos)
        .mark_line(point=True, color=COLOR_DORADO, strokeWidth=3)
        .encode(
            x=alt.X("Cliente:N", sort=orden),
            y=alt.Y(
                "Acumulado:Q",
                axis=alt.Axis(title="Participaci\u00f3n acumulada", format="%", orient="right"),
                scale=alt.Scale(domain=[0, 1]),
            ),
            tooltip=["Cliente", alt.Tooltip("Acumulado:Q", format=".1%")],
        )
    )
    return (barras + linea).resolve_scale(y="independent").properties(
        title=f"Pareto de clientes · Top {top_n}",
        height=390,
    )


def grafico_mapa_cliente_estilo(
    df: pd.DataFrame,
    top_n: int,
) -> alt.TopLevelMixin | None:
    if df.empty:
        return None
    clientes = df.groupby("Cliente")["Litros_totales"].sum().nlargest(top_n).index.tolist()
    estilos = df.groupby("Estilo")["Litros_totales"].sum().nlargest(min(top_n, 10)).index.tolist()
    datos = (
        df[df["Cliente"].isin(clientes) & df["Estilo"].isin(estilos)]
        .groupby(["Cliente", "Estilo"], as_index=False)["Litros_totales"]
        .sum()
        .rename(columns={"Litros_totales": "Litros"})
    )
    if datos.empty:
        return None
    return (
        alt.Chart(datos)
        .mark_rect(cornerRadius=2)
        .encode(
            x=alt.X("Estilo:N", sort=estilos, title="Estilo"),
            y=alt.Y("Cliente:N", sort=clientes, title="Cliente"),
            color=alt.Color("Litros:Q", scale=alt.Scale(scheme="yellowgreenblue"), title="Litros"),
            tooltip=["Cliente", "Estilo", alt.Tooltip("Litros:Q", format=",.2f")],
        )
        .properties(title="Mapa de calor: clientes y estilos", height=max(360, len(clientes) * 31))
    )


def grafico_mensual_presentacion(df: pd.DataFrame) -> alt.TopLevelMixin | None:
    if df.empty:
        return None
    datos = df.copy()
    datos["Mes"] = datos["Fecha"].dt.to_period("M").dt.to_timestamp()
    datos = (
        datos.groupby(["Mes", "Tipo"], as_index=False)["Litros_totales"]
        .sum()
        .rename(columns={"Litros_totales": "Litros"})
    )
    return (
        alt.Chart(datos)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("yearmonth(Mes):T", title="Mes"),
            y=alt.Y("Litros:Q", title="Litros despachados"),
            color=alt.Color("Tipo:N", scale=escala_presentacion(), title="Presentaci\u00f3n"),
            tooltip=[
                alt.Tooltip("yearmonth(Mes):T", title="Mes", format="%b %Y"),
                "Tipo",
                alt.Tooltip("Litros:Q", format=",.2f"),
            ],
        )
        .properties(title="Comparaci\u00f3n mensual de despachos", height=390)
    )


def grafico_area_estilos(
    df: pd.DataFrame,
    top_n: int,
) -> alt.TopLevelMixin | None:
    if df.empty:
        return None
    principales = df.groupby("Estilo")["Litros_totales"].sum().nlargest(top_n).index
    datos = df[df["Estilo"].isin(principales)].copy()
    datos["Dia"] = datos["Fecha"].dt.floor("D")
    datos = (
        datos.groupby(["Dia", "Estilo"], as_index=False)["Litros_totales"]
        .sum()
        .rename(columns={"Litros_totales": "Litros"})
    )
    return (
        alt.Chart(datos)
        .mark_area(opacity=.78, interpolate="monotone")
        .encode(
            x=alt.X("Dia:T", title="Fecha"),
            y=alt.Y("Litros:Q", stack="zero", title="Litros"),
            color=alt.Color("Estilo:N", scale=escala_estilos(datos["Estilo"].tolist()), title="Estilo"),
            tooltip=[
                alt.Tooltip("Dia:T", format="%d/%m/%Y", title="Fecha"),
                "Estilo",
                alt.Tooltip("Litros:Q", format=",.2f"),
            ],
        )
        .properties(title=f"Evoluci\u00f3n diaria por estilo · Top {top_n}", height=400)
    )


def grafico_tendencia_presentacion(df: pd.DataFrame) -> alt.TopLevelMixin | None:
    if df.empty:
        return None
    datos = df.copy()
    datos["Dia"] = datos["Fecha"].dt.floor("D")
    datos = (
        datos.groupby(["Dia", "Tipo"], as_index=False)["Litros_totales"]
        .sum()
        .rename(columns={"Litros_totales": "Litros"})
    )
    return (
        alt.Chart(datos)
        .mark_line(point=True, strokeWidth=3)
        .encode(
            x=alt.X("Dia:T", title="Fecha"),
            y=alt.Y("Litros:Q", title="Litros despachados"),
            color=alt.Color("Tipo:N", scale=escala_presentacion(), title="Presentaci\u00f3n"),
            tooltip=[
                alt.Tooltip("Dia:T", format="%d/%m/%Y", title="Fecha"),
                "Tipo",
                alt.Tooltip("Litros:Q", format=",.2f"),
            ],
        )
        .properties(title="Tendencia diaria por presentaci\u00f3n", height=360)
    )


def grafico_media_movil(df: pd.DataFrame) -> alt.TopLevelMixin | None:
    if df.empty:
        return None
    datos = df.copy()
    datos["Dia"] = datos["Fecha"].dt.floor("D")
    diario = (
        datos.groupby("Dia", as_index=False)["Litros_totales"]
        .sum()
        .sort_values("Dia")
        .rename(columns={"Litros_totales": "Litros diarios"})
    )
    diario["Promedio 7 dias"] = diario["Litros diarios"].rolling(7, min_periods=1).mean()
    largo = diario.melt(
        id_vars="Dia",
        value_vars=["Litros diarios", "Promedio 7 dias"],
        var_name="Serie",
        value_name="Litros",
    )
    return (
        alt.Chart(largo)
        .mark_line(point=True, strokeWidth=3)
        .encode(
            x=alt.X("Dia:T", title="Fecha"),
            y=alt.Y("Litros:Q", title="Litros"),
            color=alt.Color(
                "Serie:N",
                scale=alt.Scale(
                    domain=["Litros diarios", "Promedio 7 dias"],
                    range=["#B7C9C1", COLOR_PRIMARIO],
                ),
                title="Serie",
            ),
            tooltip=[
                alt.Tooltip("Dia:T", format="%d/%m/%Y", title="Fecha"),
                "Serie",
                alt.Tooltip("Litros:Q", format=",.2f"),
            ],
        )
        .properties(title="Litros diarios y promedio m\u00f3vil de 7 d\u00edas", height=360)
    )


def grafico_dia_semana(df: pd.DataFrame) -> alt.TopLevelMixin | None:
    if df.empty:
        return None
    datos = df.copy()
    datos["Orden"] = datos["Fecha"].dt.dayofweek
    datos["Dia semana"] = datos["Orden"].map(dict(enumerate(ORDEN_DIAS)))
    datos = (
        datos.groupby(["Orden", "Dia semana"], as_index=False)["Litros_totales"]
        .sum()
        .sort_values("Orden")
        .rename(columns={"Litros_totales": "Litros"})
    )
    return (
        alt.Chart(datos)
        .mark_bar(color=COLOR_PRIMARIO, cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X("Dia semana:N", sort=ORDEN_DIAS, title=None),
            y=alt.Y("Litros:Q", title="Litros despachados"),
            tooltip=["Dia semana", alt.Tooltip("Litros:Q", format=",.2f")],
        )
        .properties(title="Despachos por d\u00eda de la semana", height=340)
    )


def grafico_mapa_horario(df: pd.DataFrame) -> alt.TopLevelMixin | None:
    if df.empty:
        return None
    datos = df.copy()
    datos["Orden"] = datos["Fecha"].dt.dayofweek
    datos["Dia semana"] = datos["Orden"].map(dict(enumerate(ORDEN_DIAS)))
    datos["Hora"] = datos["Fecha"].dt.hour
    datos = (
        datos.groupby(["Orden", "Dia semana", "Hora"], as_index=False)["Litros_totales"]
        .sum()
        .rename(columns={"Litros_totales": "Litros"})
    )
    return (
        alt.Chart(datos)
        .mark_rect(cornerRadius=2)
        .encode(
            x=alt.X("Hora:O", title="Hora del d\u00eda"),
            y=alt.Y("Dia semana:N", sort=ORDEN_DIAS, title=None),
            color=alt.Color("Litros:Q", scale=alt.Scale(scheme="yellowgreenblue"), title="Litros"),
            tooltip=["Dia semana", "Hora", alt.Tooltip("Litros:Q", format=",.2f")],
        )
        .properties(title="Mapa de calor de actividad por d\u00eda y hora", height=340)
    )


def graficos_unidades_por_estilo(
    df: pd.DataFrame,
    top_n: int,
) -> tuple[alt.TopLevelMixin | None, alt.TopLevelMixin | None]:
    barriles = (
        df.groupby("Estilo", as_index=False)["Barriles"]
        .sum()
        .sort_values("Barriles", ascending=False)
        .head(top_n)
    )
    barriles = barriles[barriles["Barriles"].gt(0)]
    latas = (
        df.groupby("Estilo", as_index=False)["Latas"]
        .sum()
        .sort_values("Latas", ascending=False)
        .head(top_n)
    )
    latas = latas[latas["Latas"].gt(0)]

    grafico_barriles = None
    if not barriles.empty:
        grafico_barriles = (
            alt.Chart(barriles)
            .mark_bar(cornerRadiusEnd=5)
            .encode(
                y=alt.Y("Estilo:N", sort="-x", title=None),
                x=alt.X("Barriles:Q", title="Barriles despachados"),
                color=alt.Color("Estilo:N", scale=escala_estilos(barriles["Estilo"].tolist()), legend=None),
                tooltip=["Estilo", alt.Tooltip("Barriles:Q", format=",.0f")],
            )
            .properties(title="Barriles despachados por estilo", height=max(330, len(barriles) * 28))
        )

    grafico_latas = None
    if not latas.empty:
        grafico_latas = (
            alt.Chart(latas)
            .mark_bar(cornerRadiusEnd=5)
            .encode(
                y=alt.Y("Estilo:N", sort="-x", title=None),
                x=alt.X("Latas:Q", title="Latas despachadas"),
                color=alt.Color("Estilo:N", scale=escala_estilos(latas["Estilo"].tolist()), legend=None),
                tooltip=["Estilo", alt.Tooltip("Latas:Q", format=",.0f")],
            )
            .properties(title="Latas despachadas por estilo", height=max(330, len(latas) * 28))
        )

    return grafico_barriles, grafico_latas


def mostrar_despachos(df_despachos: pd.DataFrame) -> None:
    st.subheader("\U0001F69A Reporte de despachos de barriles y latas")
    st.markdown(
        """
        <div class="section-note">
        Este m\u00f3dulo une los despachos de <b>DatosM</b> y <b>VLatas</b>. Los filtros de la
        barra lateral afectan indicadores, tablas y todos los gr\u00e1ficos de esta secci\u00f3n.
        </div>
        """,
        unsafe_allow_html=True,
    )

    filtrado, fecha_inicio, fecha_fin, top_n = aplicar_filtros_despachos(df_despachos)
    st.caption(
        f"Periodo mostrado: {fecha_inicio.strftime('%d/%m/%Y')} a "
        f"{fecha_fin.strftime('%d/%m/%Y')}"
    )

    if filtrado.empty:
        st.warning("No hay despachos para los filtros seleccionados.")
        return

    total_barriles = float(filtrado["Barriles"].sum())
    total_latas = float(filtrado["Latas"].sum())
    litros_barriles = float(filtrado["Litros_barriles"].sum())
    litros_latas = float(filtrado["Litros_latas"].sum())
    total_litros = litros_barriles + litros_latas
    movimientos = float(len(filtrado))
    mostrar_metricas(total_barriles, total_latas, litros_barriles, litros_latas, movimientos)

    dias_periodo = max((fecha_fin - fecha_inicio).days + 1, 1)
    promedio_diario = total_litros / dias_periodo
    promedio_movimiento = total_litros / movimientos if movimientos else 0
    col_1, col_2, col_3, col_4 = st.columns(4)
    col_1.metric("\U0001F465 Clientes atendidos", formato_numero(filtrado["Cliente"].nunique(), 0))
    col_2.metric("\U0001F3A8 Estilos despachados", formato_numero(filtrado["Estilo"].nunique(), 0))
    col_3.metric("\U0001F4C5 Promedio diario", f"{formato_numero(promedio_diario, 2)} L")
    col_4.metric("\U0001F9FE Promedio por movimiento", f"{formato_numero(promedio_movimiento, 2)} L")

    desconocidos = filtrado[
        filtrado["Tipo"].eq("Barril") & filtrado["Litros_totales"].le(0)
    ]
    if not desconocidos.empty:
        st.warning(
            f"Hay {len(desconocidos)} despacho(s) de barril cuya capacidad no pudo determinarse. "
            "Revisa que el c\u00f3digo comience por 20, 30 o 58, o registra los litros en Capacidad/Observaciones."
        )

    resumen = (
        filtrado.groupby(["Cliente", "Estilo"], as_index=False)
        .agg(
            Barriles=("Barriles", "sum"),
            Latas=("Latas", "sum"),
            Movimientos=("Tipo", "size"),
            **{
                "Litros barriles": ("Litros_barriles", "sum"),
                "Litros latas": ("Litros_latas", "sum"),
                "Litros totales": ("Litros_totales", "sum"),
            },
        )
        .sort_values("Litros totales", ascending=False)
    )
    resumen = normalizar_tipos_resumen(resumen)

    tab_panorama, tab_clientes, tab_estilos, tab_tendencias, tab_detalle = st.tabs(
        ["Panorama", "Clientes", "Estilos", "Tendencias", "Detalle"]
    )

    with tab_panorama:
        st.markdown("#### Resumen por cliente y estilo")
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar resumen CSV",
            data=resumen.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"resumen_despachos_{fecha_inicio}_{fecha_fin}.csv",
            mime="text/csv",
        )

        datos_presentacion = (
            filtrado.groupby("Tipo", as_index=False)["Litros_totales"]
            .sum()
            .rename(columns={"Litros_totales": "Litros"})
        )
        datos_estilo = (
            filtrado.groupby("Estilo", as_index=False)["Litros_totales"]
            .sum()
            .rename(columns={"Litros_totales": "Litros"})
        )
        izquierda, derecha = st.columns(2)
        with izquierda:
            mostrar_grafico(
                crear_grafico_dona(
                    datos_presentacion,
                    categoria="Tipo",
                    valor="Litros",
                    titulo="Distribuci\u00f3n por presentaci\u00f3n",
                    modo_color="presentacion",
                )
            )
        with derecha:
            mostrar_grafico(
                crear_grafico_dona(
                    datos_estilo,
                    categoria="Estilo",
                    valor="Litros",
                    titulo="Distribuci\u00f3n por estilo",
                )
            )
        mostrar_grafico(grafico_mensual_presentacion(filtrado))

    with tab_clientes:
        mostrar_grafico(
            grafico_litros_por_categoria(
                filtrado,
                categoria="Cliente",
                titulo=f"Litros despachados por cliente · Top {top_n}",
                top_n=top_n,
            )
        )
        izquierda, derecha = st.columns([1.05, 1])
        with izquierda:
            mostrar_grafico(grafico_pareto_clientes(filtrado, top_n))
        with derecha:
            mostrar_grafico(grafico_mapa_cliente_estilo(filtrado, min(top_n, 12)))

    with tab_estilos:
        mostrar_grafico(
            grafico_litros_por_categoria(
                filtrado,
                categoria="Estilo",
                titulo=f"Litros despachados por estilo · Top {top_n}",
                top_n=top_n,
            )
        )
        grafico_barriles, grafico_latas = graficos_unidades_por_estilo(filtrado, top_n)
        col_barriles, col_latas = st.columns(2)
        with col_barriles:
            mostrar_grafico(grafico_barriles)
        with col_latas:
            mostrar_grafico(grafico_latas)
        mostrar_grafico(grafico_area_estilos(filtrado, top_n))

    with tab_tendencias:
        izquierda, derecha = st.columns(2)
        with izquierda:
            mostrar_grafico(grafico_tendencia_presentacion(filtrado))
        with derecha:
            mostrar_grafico(grafico_media_movil(filtrado))
        izquierda, derecha = st.columns(2)
        with izquierda:
            mostrar_grafico(grafico_dia_semana(filtrado))
        with derecha:
            mostrar_grafico(grafico_mapa_horario(filtrado))

    with tab_detalle:
        detalle = filtrado[
            [
                "Fecha",
                "Tipo",
                "Cliente",
                "Estilo",
                "Codigo",
                "Lote",
                "Barriles",
                "Latas",
                "Litros_barriles",
                "Litros_latas",
                "Litros_totales",
                "Responsable",
                "Observaciones",
            ]
        ].copy()
        detalle = detalle.sort_values("Fecha", ascending=False)
        detalle["Fecha"] = detalle["Fecha"].dt.strftime("%d/%m/%Y %H:%M")
        detalle = detalle.rename(
            columns={
                "Codigo": "C\u00f3digo barril",
                "Litros_barriles": "Litros barriles",
                "Litros_latas": "Litros latas",
                "Litros_totales": "Litros totales",
            }
        )
        detalle["Barriles"] = detalle["Barriles"].round().astype(int)
        detalle["Latas"] = detalle["Latas"].round().astype(int)
        for columna in ["Litros barriles", "Litros latas", "Litros totales"]:
            detalle[columna] = detalle[columna].round(2)

        st.dataframe(detalle, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar detalle CSV",
            data=detalle.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"detalle_despachos_{fecha_inicio}_{fecha_fin}.csv",
            mime="text/csv",
        )


# -----------------------------------------------------------------------------
# APLICACION PRINCIPAL
# -----------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(
        page_title="Reporte Barriles y Latas Castiza",
        page_icon="\U0001F37A",
        layout="wide",
    )
    aplicar_estilos_css()
    mostrar_encabezado()

    st.sidebar.markdown("## \U0001F37A CASTIZA")
    st.sidebar.caption("Panel de reportes e inventario")
    st.sidebar.subheader("Configuraci\u00f3n")
    umbral_alerta = st.sidebar.number_input(
        "Alerta de inventario por estilo (L)",
        min_value=0.0,
        value=UMBRAL_ALERTA_PREDETERMINADO,
        step=25.0,
        help="Un estilo aparece en alerta cuando sus litros combinados quedan por debajo de este valor.",
    )

    if st.sidebar.button("Actualizar datos desde Google Sheets", use_container_width=True):
        leer_hoja.clear()
        try:
            st.rerun()
        except AttributeError:
            st.experimental_rerun()

    with st.spinner("Consultando Google Sheets..."):
        bruto_barriles, error_barriles = cargar_hoja_segura(HOJA_BARRILES)
        bruto_latas, error_latas = cargar_hoja_segura(HOJA_MOVIMIENTOS_LATAS)
        bruto_inventario_latas, error_inventario_latas = cargar_hoja_segura(
            HOJA_INVENTARIO_LATAS
        )

    errores = []
    if error_barriles:
        errores.append(f"{HOJA_BARRILES}: {error_barriles}")
    if error_latas:
        errores.append(f"{HOJA_MOVIMIENTOS_LATAS}: {error_latas}")
    if error_inventario_latas:
        errores.append(f"{HOJA_INVENTARIO_LATAS}: {error_inventario_latas}")
    for error in errores:
        st.warning(f"No se pudo cargar {error}")

    df_barriles = preparar_barriles(bruto_barriles)
    df_movimientos_latas = preparar_movimientos_latas(bruto_latas)
    df_inventario_latas = preparar_inventario_latas(bruto_inventario_latas)

    inventario_barriles = obtener_inventario_barriles_actual(df_barriles)
    despachos = construir_despachos(df_barriles, df_movimientos_latas)

    fechas_disponibles = []
    if not df_barriles.empty:
        fechas_disponibles.append(df_barriles["Fecha"].max())
    if not df_movimientos_latas.empty:
        fechas_disponibles.append(df_movimientos_latas["Fecha"].max())
    if fechas_disponibles:
        ultima_fecha = max(fechas_disponibles)
        if pd.notna(ultima_fecha):
            st.sidebar.caption(
                "\u00daltimo movimiento: " + ultima_fecha.strftime("%d/%m/%Y %H:%M")
            )

    pestana_inventario, pestana_despachos = st.tabs(
        ["\U0001F4E6 Inventario actual", "\U0001F4CA Despachos y ventas"]
    )

    with pestana_inventario:
        mostrar_inventario_actual(
            inventario_barriles,
            df_inventario_latas,
            umbral_alerta,
        )

    with pestana_despachos:
        mostrar_despachos(despachos)

    st.markdown("---")
    st.caption(
        "Fuentes: DatosM, VLatas e InventarioLatasTR. "
        f"Conversi\u00f3n usada: 1 lata = {LITROS_POR_LATA:.3f} L."
    )


if __name__ == "__main__":
    main()
