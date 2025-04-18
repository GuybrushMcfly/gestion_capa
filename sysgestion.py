import json
from google.oauth2.service_account import Credentials
import gspread
import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from datetime import datetime
import plotly.graph_objects as go

# ---- CONFIGURACIÓN DE PÁGINA ----
st.set_page_config(page_title="Gestión Capacitación DCYCP", layout="wide")
st.sidebar.image("logo-cap.png", use_container_width=True)

modo = st.get_option("theme.base")
color_texto = "#000000" if modo == "light" else "#FFFFFF"

# ---- CARGAR CONFIGURACIÓN DESDE YAML ----
with open("config.yaml") as file:
    config = yaml.load(file, Loader=SafeLoader)

# ---- AUTENTICACIÓN ----
authenticator = stauth.Authenticate(
    credentials=config['credentials'],
    cookie_name=config['cookie']['name'],
    cookie_key=config['cookie']['key'],
    cookie_expiry_days=config['cookie']['expiry_days']
)

authenticator.login()

if st.session_state["authentication_status"]:
    authenticator.logout("Cerrar sesión", "sidebar")
    st.sidebar.success(f"Hola, {st.session_state['name']}")
    st.markdown("""<h1 style='font-size: 30px; color: white;'>Gestión Capacitación DCYCP</h1>""", unsafe_allow_html=True)
elif st.session_state["authentication_status"] is False:
    st.error("❌ Usuario o contraseña incorrectos.")
    st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning("🔒 Ingresá tus credenciales para acceder al dashboard.")
    st.stop()

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)


# ---- CARGA DE SHEETS ----
scope = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(
    json.loads(st.secrets["GOOGLE_CREDS"]),
    scopes=scope
)
gc = gspread.authorize(creds)
sh = gc.open_by_key("1uYHnALX3TCaSzqJJFESOf8OpiaxKbLFYAQdcKFqbGrk")

# Leer hojas
df_actividades = pd.DataFrame(sh.worksheet("actividades").get_all_records())
df_comisiones  = pd.DataFrame(sh.worksheet("comisiones").get_all_records())
df_seguimiento = pd.DataFrame(sh.worksheet("seguimiento").get_all_records())

# Merge para facilitar filtros
df_completo = (
    df_comisiones
    .merge(df_actividades[['Id_Actividad','NombreActividad']], on="Id_Actividad", how="left")
    .merge(df_seguimiento,           on="Id_Comision",     how="left")
)

# ---- SELECCIÓN DE CURSO Y COMISIÓN ----
curso = st.selectbox(
    "Seleccioná un Curso:",
    df_actividades["NombreActividad"].unique()
)
coms = df_completo.loc[
    df_completo["NombreActividad"] == curso, "Id_Comision"
].unique().tolist()
comision = st.selectbox("Seleccioná una Comisión:", coms)

# Obtener fila de actividad y comisión
id_act = df_actividades.loc[df_actividades["NombreActividad"] == curso, "Id_Actividad"].iloc[0]
fila_act = df_actividades.loc[df_actividades["Id_Actividad"] == id_act].iloc[0]
fila_seg = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]

# Prepare worksheets
ws_act = sh.worksheet("actividades")
header_act = ws_act.row_values(1)
row_idx_act = ws_act.find(str(id_act)).row

ws_seg = sh.worksheet("seguimiento")
header_seg = ws_seg.row_values(1)
row_idx_seg = ws_seg.find(str(comision)).row

# Colores e íconos (asegurate de hacerlo una sola vez arriba)
color_completado = "#4DB6AC"
color_actual     = "#FF8A65"
color_pendiente  = "#D3D3D3"
icono = {"finalizado":"⚪","actual":"⏳","pendiente":"⚪"}

# 1) Formulario de edición
with st.expander("🛠️ Editar APROBACIÓN ACTIVIDAD"):
    with st.form("form_aprob"):
        cambios = []
        for col, label in pasos_act:
            marcado = bool(fila_act[col])
            chk = st.checkbox(label, value=marcado, disabled=marcado, key=f"fa_{col}")
            if chk and not marcado:
                cambios.append(col)

        if st.form_submit_button("💾 Actualizar APROBACIÓN"):
            # ... tu código de update_ws_act aquí ...
            # luego recarga fila_act:
            df_act = pd.DataFrame(ws_act.get_all_records())
            fila_act = df_act.loc[df_act["Id_Actividad"] == id_act].iloc[0]
            st.success("✅ Aprobación actualizada!")

# 2) STEPPER FIJO DE APROBACIÓN (ahora **después** del form)
# Recalculamos el índice actual
bools_act = [ bool(fila_act[col]) for col,_ in pasos_act ]
if all(bools_act):
    idx_act = len(bools_act)
else:
    idx_act = next(i for i,v in enumerate(bools_act) if not v)

# Dibujamos el gráfico
fig_act = go.Figure()
x = list(range(len(pasos_act))); y = 1

# Líneas
for i in range(len(pasos_act)-1):
    clr = color_completado if i < idx_act else color_pendiente
    fig_act.add_trace(go.Scatter(
        x=[x[i], x[i+1]], y=[y, y],
        mode="lines",
        line=dict(color=clr, width=8),
        showlegend=False
    ))

# Puntos e íconos con hover
for i, (col, label) in enumerate(pasos_act):
    if i < idx_act:
        clr, ic = color_completado, icono["finalizado"]
    elif i == idx_act:
        clr, ic = color_actual,     icono["actual"]
    else:
        clr, ic = color_pendiente,  icono["pendiente"]

    user = fila_act.get(f"{col}_user", "")
    ts   = fila_act.get(f"{col}_timestamp", "")
    hover = f"{label}<br>Por: {user}<br>El: {ts}"

    fig_act.add_trace(go.Scatter(
        x=[x[i]], y=[y],
        mode="markers+text",
        marker=dict(size=45, color=clr),
        text=[ic],
        textposition="middle center",
        textfont=dict(color="white", size=18),
        hovertext=[hover],
        hoverinfo="text",
        showlegend=False
    ))
    fig_act.add_trace(go.Scatter(
        x=[x[i]], y=[y-0.15],
        mode="text",
        text=[label],
        textposition="bottom center",
        textfont=dict(color="white", size=12),
        showlegend=False
    ))

fig_act.update_layout(
    title=dict(text="🔹 APROBACIÓN ACTIVIDAD", x=0.01, xanchor="left", font=dict(size=16)),
    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.3,1.2]),
    height=180, margin=dict(l=20, r=20, t=30, b=0),
)
st.plotly_chart(fig_act)


