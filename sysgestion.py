import json
from google.oauth2.service_account import Credentials
import gspread
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from streamlit_echarts import st_echarts
#import seaborn as sns

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

# ---- CONFIGURACION ----
st.set_page_config(page_title="Gestión Capacitación DCYCP", layout="wide")

# ---- CREDENCIALES Y CARGA DE DATOS ----
scope = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(
    json.loads(st.secrets["GOOGLE_CREDS"]), scopes=scope
)
gc = gspread.authorize(creds)
sh = gc.open_by_key("1uYHnALX3TCaSzqJJFESOf8OpiaxKbLFYAQdcKFqbGrk")

# Leer hojas
ws_act = sh.worksheet("actividades")
ws_seg = sh.worksheet("seguimiento")
df_actividades = pd.DataFrame(ws_act.get_all_records())
df_comisiones = pd.DataFrame(sh.worksheet("comisiones").get_all_records())
df_seguimiento = pd.DataFrame(ws_seg.get_all_records())

# Merge para filtros
df_completo = (
    df_comisiones
    .merge(df_actividades[['Id_Actividad','NombreActividad']], on="Id_Actividad", how="left")
    .merge(df_seguimiento, on="Id_Comision", how="left")
)

# ---- SELECCION DE CURSO Y COMISION ----
curso = st.selectbox("Seleccioná un Curso:", df_actividades["NombreActividad"].unique())
coms = df_completo.loc[df_completo["NombreActividad"] == curso, "Id_Comision"].unique().tolist()
comision = st.selectbox("Seleccioná una Comisión:", coms)

# Filas y headers
id_act = df_actividades.loc[df_actividades["NombreActividad"] == curso, "Id_Actividad"].iloc[0]
fila_act = df_actividades.loc[df_actividades["Id_Actividad"] == id_act].iloc[0]
fila_seg = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]

header_act = ws_act.row_values(1)
row_idx_act = ws_act.find(str(id_act)).row

header_seg = ws_seg.row_values(1)
row_idx_seg = ws_seg.find(str(comision)).row

# ---- CONFIG PROCESOS ----
procesos = {
    "CAMPUS": [
        ("C_ArmadoAula", "Armado Aula"),
        ("C_Matriculacion", "Matriculación participantes"),
        ("C_AperturaCurso", "Apertura Curso"),
        ("C_CierreCurso", "Cierre Curso"),
        ("C_AsistenciaEvaluacion", "Entrega Notas y Asistencia"),
    ],
    "DICTADO COMISION": [
        ("D_Difusion", "Difusión"),
        ("D_AsignacionVacantes", "Asignación Vacantes"),
        ("D_Cursada", "Cursada"),
        ("D_AsistenciaEvaluacion", "Asistencia y Evaluación"),
        ("D_CreditosSAI", "Créditos SAI"),
        ("D_Liquidacion", "Liquidación"),
    ]
}

# ---- COLORES Y ICONOS ----
color_completado = "#4DB6AC"
color_actual = "#FF8A65"
color_pendiente = "#D3D3D3"
icono = {"finalizado": "⚪", "actual": "⏳", "pendiente": "⚪"}

# ---- BARRA DE ACTIVIDAD ----
pasos_act = [
    ("A_Diseño", "Diseño"),
    ("A_AutorizacionINAP", "Autorización INAP"),
    ("A_CargaSAI", "Carga SAI"),
    ("A_TramitacionExpediente", "Tramitación Expediente"),
    ("A_DictamenINAP", "Dictamen INAP")
]

bools_act = [bool(fila_act[col]) for col, _ in pasos_act]
idx_act = len(bools_act) if all(bools_act) else next(i for i, v in enumerate(bools_act) if not v)

fig_act = go.Figure()
x_act = list(range(len(pasos_act))); y = 1

for i in range(len(pasos_act) - 1):
    clr = color_completado if i < idx_act else color_pendiente
    fig_act.add_trace(go.Scatter(x=[x_act[i], x_act[i+1]], y=[y,y], mode="lines", line=dict(color=clr, width=8), showlegend=False))

for i, (col, label) in enumerate(pasos_act):
    clr, ic = (
        (color_completado, icono["finalizado"]) if i < idx_act else
        (color_actual, icono["actual"]) if i == idx_act else
        (color_pendiente, icono["pendiente"])
    )
    hover = f"{label}<br>Por: {fila_act.get(col + '_user','')}<br>El: {fila_act.get(col + '_timestamp','')}"
    fig_act.add_trace(go.Scatter(x=[x_act[i]], y=[y], mode="markers+text", marker=dict(size=45, color=clr),
                                 text=[ic], textposition="middle center", textfont=dict(color="white", size=18),
                                 hovertext=[hover], hoverinfo="text", showlegend=False))
    fig_act.add_trace(go.Scatter(x=[x_act[i]], y=[y-0.15], mode="text", text=[label],
                                 textposition="bottom center", textfont=dict(color="white", size=12), showlegend=False))

fig_act.update_layout(title=dict(text="🔹 APROBACIÓN ACTIVIDAD (Actividad)", x=0.01, xanchor="left", font=dict(size=16)),
                      xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                      yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.3,1.2]),
                      height=180, margin=dict(l=20, r=20, t=30, b=0))
st.plotly_chart(fig_act)

# ---- BARRAS Y FORMULARIOS POR PROCESO ----
for proc, pasos in procesos.items():
    st.markdown(f"### 🔹 {proc}")

    bools = [bool(fila_seg[col]) for col, _ in pasos]
    idx = len(bools) if all(bools) else next(i for i, v in enumerate(bools) if not v)
    fig = go.Figure(); x = list(range(len(pasos))); y = 1

    for i in range(len(pasos)-1):
        clr = color_completado if i < idx else color_pendiente
        fig.add_trace(go.Scatter(x=[x[i], x[i+1]], y=[y,y], mode="lines",
                                 line=dict(color=clr, width=8), showlegend=False))

    for i, (col, label) in enumerate(pasos):
        clr, ic = (
            (color_completado, icono["finalizado"]) if i < idx else
            (color_actual, icono["actual"]) if i == idx else
            (color_pendiente, icono["pendiente"])
        )
        hover = f"{label}<br>Por: {fila_seg.get(col+'_user','')}<br>El: {fila_seg.get(col+'_timestamp','')}"
        fig.add_trace(go.Scatter(x=[x[i]], y=[y], mode="markers+text",
                                 marker=dict(size=45, color=clr),
                                 text=[ic], textposition="middle center",
                                 textfont=dict(color="white", size=18),
                                 hovertext=[hover], hoverinfo="text",
                                 showlegend=False))
        fig.add_trace(go.Scatter(x=[x[i]], y=[y-0.15], mode="text",
                                 text=[label], textposition="bottom center",
                                 textfont=dict(color="white", size=12), showlegend=False))

    fig.update_layout(
        title=dict(text=f"", x=0.01, xanchor="left", font=dict(size=16)),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.3, 1.2]),
        height=180, margin=dict(l=20, r=20, t=10, b=0))
    st.plotly_chart(fig)

    if f"editar_{proc}" not in st.session_state:
        st.session_state[f"editar_{proc}"] = False

    if not st.session_state[f"editar_{proc}"]:
        if st.button(f"✏️ Editar {proc}", key=f"btn_editar_{proc}"):
            st.session_state[f"editar_{proc}"] = True
    else:
        with st.form(f"form_{proc}"):
            cambios = []
            for i, (col, label) in enumerate(pasos):
                val = bool(fila_seg[col])
                habilitado = not val and all(bool(fila_seg[pasos[k][0]]) for k in range(i))
                new = st.checkbox(label, value=val, disabled=not habilitado, key=f"{comision}_{proc}_{col}")
                if new and not val:
                    cambios.append(col)
            submitted = st.form_submit_button("💾 Actualizar cambios")
        if submitted and cambios:
            for col in cambios:
                ws = ws_seg
                hdr = header_seg
                ridx = row_idx_seg
                try:
                    cidx = hdr.index(col) + 1
                    ws.update_cell(ridx, cidx, True)
                    ucol = f"{col}_user"; uidx = hdr.index(ucol) + 1
                    ws.update_cell(ridx, uidx, st.session_state.get("name", "Anon"))
                    tcol = f"{col}_timestamp"; tidx = hdr.index(tcol) + 1
                    now = datetime.now().isoformat(sep=" ", timespec="seconds")
                    ws.update_cell(ridx, tidx, now)
                except Exception as e:
                    st.error(f"Error {col}: {e}")
            df_seguimiento = pd.DataFrame(ws_seg.get_all_records())
            fila_seg = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]
            st.success("✅ Cambios guardados.")
            st.session_state[f"editar_{proc}"] = False
