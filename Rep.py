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
    for columna in ["Barriles", "Latas"]:
        if columna in resultado.columns:
            resultado[columna] = resultado[columna].fillna(0).round().astype(int)
    for columna in ["Litros barriles", "Litros latas", "Litros totales"]:
        if columna in resultado.columns:
            resultado[columna] = resultado[columna].fillna(0).round(2)
    return resultado


def mostrar_metricas(
    barriles: float,
    latas: float,
    litros_barriles: float,
    litros_latas: float,
) -> None:
    litros_totales = litros_barriles + litros_latas
    columnas = st.columns(5)
    columnas[0].metric("Barriles", formato_numero(barriles, 0))
    columnas[1].metric("Latas", formato_numero(latas, 0))
    columnas[2].metric("Litros en barriles", f"{formato_numero(litros_barriles, 1)} L")
    columnas[3].metric("Litros en latas", f"{formato_numero(litros_latas, 2)} L")
    columnas[4].metric("Litros totales", f"{formato_numero(litros_totales, 2)} L")


def grafico_litros_por_categoria(
    df: pd.DataFrame,
    categoria: str,
    titulo: str,
) -> None:
    if df.empty:
        st.info("No hay datos para generar el grafico.")
        return

    agrupado = (
        df.groupby([categoria, "Tipo"], as_index=False)["Litros_totales"]
        .sum()
        .rename(columns={"Litros_totales": "Litros"})
    )

    grafico = (
        alt.Chart(agrupado)
        .mark_bar()
        .encode(
            y=alt.Y(f"{categoria}:N", sort="-x", title=categoria),
            x=alt.X("Litros:Q", title="Litros"),
            color=alt.Color("Tipo:N", title="Presentación"),
            tooltip=[categoria, "Tipo", alt.Tooltip("Litros:Q", format=",.2f")],
        )
        .properties(title=titulo, height=max(320, len(agrupado[categoria].unique()) * 24))
    )
    st.altair_chart(grafico, use_container_width=True)


def aplicar_filtros_despachos(df: pd.DataFrame) -> tuple[pd.DataFrame, date, date]:
    if df.empty:
        hoy = hoy_bogota()
        return df, hoy, hoy

    minimo = df["Fecha"].min().date()
    maximo = df["Fecha"].max().date()
    hoy = hoy_bogota()

    st.sidebar.markdown("---")
    st.sidebar.subheader("Filtros de despachos")
    periodo = st.sidebar.selectbox(
        "Periodo",
        ["Mes actual", "Año actual", "Todo el historial", "Rango personalizado"],
    )

    if periodo == "Mes actual":
        fecha_inicio = date(hoy.year, hoy.month, 1)
        fecha_fin = hoy
    elif periodo == "Año actual":
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
        )
        fecha_fin = st.sidebar.date_input(
            "Fecha final",
            value=min(hoy, maximo),
            min_value=minimo,
            max_value=maximo,
        )

    if fecha_inicio > fecha_fin:
        fecha_inicio, fecha_fin = fecha_fin, fecha_inicio

    clientes = sorted(df["Cliente"].dropna().astype(str).unique().tolist())
    estilos = sorted(df["Estilo"].dropna().astype(str).unique().tolist())

    cliente = st.sidebar.selectbox("Cliente", ["Todos"] + clientes)
    estilo = st.sidebar.selectbox("Estilo", ["Todos"] + estilos)
    presentacion = st.sidebar.selectbox("Presentación", ["Todas", "Barril", "Lata"])

    filtrado = df[
        df["Fecha"].dt.date.between(fecha_inicio, fecha_fin, inclusive="both")
    ].copy()

    if cliente != "Todos":
        filtrado = filtrado[filtrado["Cliente"].eq(cliente)]
    if estilo != "Todos":
        filtrado = filtrado[filtrado["Estilo"].eq(estilo)]
    if presentacion != "Todas":
        filtrado = filtrado[filtrado["Tipo"].eq(presentacion)]

    return filtrado, fecha_inicio, fecha_fin


# -----------------------------------------------------------------------------
# VISTA: INVENTARIO ACTUAL
# -----------------------------------------------------------------------------
def mostrar_inventario_actual(
    inventario_barriles: pd.DataFrame,
    inventario_latas: pd.DataFrame,
) -> None:
    st.subheader("Inventario actual en cuarto frío")
    st.caption(
        "Barriles: último estado registrado por código. Latas: saldo de InventarioLatasTR. "
        f"Cada lata equivale a {LITROS_POR_LATA:.3f} L."
    )

    total_barriles = float(len(inventario_barriles))
    total_latas = float(inventario_latas["Disponible"].sum()) if not inventario_latas.empty else 0.0
    litros_barriles = float(inventario_barriles["Litros"].sum()) if not inventario_barriles.empty else 0.0
    litros_latas = float(inventario_latas["Litros"].sum()) if not inventario_latas.empty else 0.0
    mostrar_metricas(total_barriles, total_latas, litros_barriles, litros_latas)

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
    if not resumen.empty:
        resumen["Litros totales"] = resumen["Litros barriles"] + resumen["Litros latas"]
        resumen = normalizar_tipos_resumen(resumen)
        resumen = resumen.sort_values("Litros totales", ascending=False)

        st.markdown("#### Resumen por estilo")
        st.dataframe(resumen, use_container_width=True, hide_index=True)

        grafico = resumen.melt(
            id_vars="Estilo",
            value_vars=["Litros barriles", "Litros latas"],
            var_name="Presentación",
            value_name="Litros",
        )
        grafico["Presentación"] = grafico["Presentación"].replace(
            {"Litros barriles": "Barril", "Litros latas": "Lata"}
        )
        grafico_altair = (
            alt.Chart(grafico)
            .mark_bar()
            .encode(
                y=alt.Y("Estilo:N", sort="-x"),
                x=alt.X("Litros:Q", title="Litros disponibles"),
                color=alt.Color("Presentación:N", title="Presentación"),
                tooltip=["Estilo", "Presentación", alt.Tooltip("Litros:Q", format=",.2f")],
            )
            .properties(height=max(320, len(resumen) * 28))
        )
        st.altair_chart(grafico_altair, use_container_width=True)
    else:
        st.warning("No se encontraron existencias actuales.")

    columna_barriles, columna_latas = st.columns(2)
    with columna_barriles:
        with st.expander("Detalle de barriles en cuarto frío", expanded=False):
            if inventario_barriles.empty:
                st.info("No hay barriles registrados en cuarto frío.")
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
        with st.expander("Detalle de latas disponibles", expanded=False):
            if inventario_latas.empty:
                st.info("No hay latas disponibles.")
            else:
                detalle = inventario_latas[
                    ["Estilo", "Lote", "Ingresadas", "Despachadas", "Devoluciones", "Bajas", "Disponible", "Litros"]
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
# VISTA: DESPACHOS
# -----------------------------------------------------------------------------
def mostrar_despachos(df_despachos: pd.DataFrame) -> None:
    st.subheader("Reporte de despachos de barriles y latas")
    st.caption(
        "Se cuentan movimientos con estado Despacho. En VLatas, los registros historicos "
        "sin estado tambien se consideran despachos."
    )

    filtrado, fecha_inicio, fecha_fin = aplicar_filtros_despachos(df_despachos)
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
    mostrar_metricas(total_barriles, total_latas, litros_barriles, litros_latas)

    desconocidos = filtrado[
        filtrado["Tipo"].eq("Barril") & filtrado["Litros_totales"].le(0)
    ]
    if not desconocidos.empty:
        st.warning(
            f"Hay {len(desconocidos)} despacho(s) de barril cuya capacidad no pudo determinarse. "
            "Revisa que el codigo comience por 20, 30 o 58, o registra los litros en Capacidad/Observaciones."
        )

    resumen = (
        filtrado.groupby(["Cliente", "Estilo"], as_index=False)
        .agg(
            Barriles=("Barriles", "sum"),
            Latas=("Latas", "sum"),
            **{
                "Litros barriles": ("Litros_barriles", "sum"),
                "Litros latas": ("Litros_latas", "sum"),
                "Litros totales": ("Litros_totales", "sum"),
            },
        )
        .sort_values("Litros totales", ascending=False)
    )
    resumen = normalizar_tipos_resumen(resumen)

    pestana_resumen, pestana_graficos, pestana_detalle = st.tabs(
        ["Resumen", "Graficos", "Detalle de movimientos"]
    )

    with pestana_resumen:
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        csv_resumen = resumen.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Descargar resumen CSV",
            data=csv_resumen,
            file_name=f"resumen_despachos_{fecha_inicio}_{fecha_fin}.csv",
            mime="text/csv",
        )

    with pestana_graficos:
        grafico_litros_por_categoria(
            filtrado,
            categoria="Cliente",
            titulo="Litros despachados por cliente",
        )
        grafico_litros_por_categoria(
            filtrado,
            categoria="Estilo",
            titulo="Litros despachados por estilo",
        )

        tendencia = filtrado.copy()
        tendencia["Dia"] = tendencia["Fecha"].dt.floor("D")
        tendencia = (
            tendencia.groupby(["Dia", "Tipo"], as_index=False)["Litros_totales"]
            .sum()
            .rename(columns={"Litros_totales": "Litros"})
        )
        grafico_tendencia = (
            alt.Chart(tendencia)
            .mark_line(point=True)
            .encode(
                x=alt.X("Dia:T", title="Fecha"),
                y=alt.Y("Litros:Q", title="Litros despachados"),
                color=alt.Color("Tipo:N", title="Presentación"),
                tooltip=[
                    alt.Tooltip("Dia:T", title="Fecha", format="%d/%m/%Y"),
                    "Tipo",
                    alt.Tooltip("Litros:Q", format=",.2f"),
                ],
            )
            .properties(title="Tendencia diaria de despachos", height=380)
        )
        st.altair_chart(grafico_tendencia, use_container_width=True)

    with pestana_detalle:
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
                "Codigo": "Codigo barril",
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
        csv_detalle = detalle.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Descargar detalle CSV",
            data=csv_detalle,
            file_name=f"detalle_despachos_{fecha_inicio}_{fecha_fin}.csv",
            mime="text/csv",
        )


# -----------------------------------------------------------------------------
# APLICACION PRINCIPAL
# -----------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(
        page_title="Reporte Barriles y Latas Castiza",
        page_icon="🍺",
        layout="wide",
    )

    st.markdown(
        "<h1 style='text-align:center; color:#20cb80;'>"
        "🍺 REPORTE DE BARRILES Y LATAS - CASTIZA"
        "</h1>",
        unsafe_allow_html=True,
    )

    st.sidebar.header("Actualizacion")
    if st.sidebar.button("Actualizar datos desde Google Sheets"):
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

    pestana_inventario, pestana_despachos = st.tabs(
        ["Inventario actual", "Despachos y ventas"]
    )

    with pestana_inventario:
        mostrar_inventario_actual(inventario_barriles, df_inventario_latas)

    with pestana_despachos:
        mostrar_despachos(despachos)

    st.markdown("---")
    st.caption(
        "Fuentes: DatosM, VLatas e InventarioLatasTR. "
        f"Conversion usada: 1 lata = {LITROS_POR_LATA:.3f} L."
    )


if __name__ == "__main__":
    main()
