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
