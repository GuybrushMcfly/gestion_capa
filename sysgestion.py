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

# Colores e iconos
col_ok, col_now, col_ng = "#4DB6AC", "#FF8A65", "#D3D3D3"
icono = {"finalizado":"⚪","actual":"⏳","pendiente":"⚪"}

# ---- STEPPER FIJO: APROBACIÓN ACTIVIDAD ----
pasos_act = [
    ("A_Diseño","Diseño"),
    ("A_AutorizacionINAP","Autorización INAP"),
    ("A_CargaSAI","Carga SAI"),
    ("A_TramitacionExpediente","Tramitación Expediente"),
    ("A_DictamenINAP","Dictamen INAP"),
]
bools = [ bool(fila_act[c]) for c,_ in pasos_act ]
idx   = len(bools) if all(bools) else next(i for i,v in enumerate(bools) if not v)

fig = go.Figure(); x = list(range(len(pasos_act))); y=1
# líneas
for i in range(len(pasos_act)-1):
    clr = col_ok if i<idx else col_ng
    fig.add_trace(go.Scatter(x=[x[i],x[i+1]], y=[y,y], mode="lines",
                              line=dict(color=clr,width=8), showlegend=False))
# círculos
for i,(c,label) in enumerate(pasos_act):
    clr,ic = (
        (col_ok,   icono["finalizado"]) if i<idx else
        (col_now,  icono["actual"])     if i==idx else
        (col_ng,   icono["pendiente"])
    )
    user = fila_act.get(f"{c}_user","")
    ts   = fila_act.get(f"{c}_timestamp","")
    hover = f"{label}<br>Por: {user}<br>El: {ts}"
    fig.add_trace(go.Scatter(x=[x[i]], y=[y], mode="markers+text",
                              marker=dict(size=45,color=clr),
                              text=[ic], textposition="middle center",
                              textfont=dict(color="white",size=18),
                              hovertext=[hover], hoverinfo="text", showlegend=False))
    fig.add_trace(go.Scatter(x=[x[i]], y=[y-0.15], mode="text",
                              text=[label], textposition="bottom center",
                              textfont=dict(color="white",size=12), showlegend=False))

fig.update_layout(
    title=dict(text="🔹 APROBACIÓN ACTIVIDAD", x=0.01, xanchor="left", font=dict(size=16)),
    xaxis=dict(showgrid=False,zeroline=False,showticklabels=False),
    yaxis=dict(showgrid=False,zeroline=False,showticklabels=False,range=[0.3,1.2]),
    height=180, margin=dict(l=20,r=20,t=30,b=0)
)
st.plotly_chart(fig)

# ---- FORMULARIOS SEPARADOS POR PROCESO ----

# 1) APROBACIÓN ACTIVIDAD (editar)
with st.expander("🛠️ Editar APROBACIÓN ACTIVIDAD"):
    with st.form("form_aprob"):
        cambios = []
        for c,label in pasos_act:
            val = bool(fila_act[c])
            chk = st.checkbox(label, value=val, disabled=val, key=f"fa_{c}")
            if chk and not val:
                cambios.append(c)
        if st.form_submit_button("💾 Actualizar APROBACIÓN"):
            errs=[]
            for col in cambios:
                try:
                    # booleano
                    i_col = header_act.index(col)+1
                    ws_act.update_cell(row_idx_act, i_col, True)
                    # user
                    u_col = f"{col}_user"; i_u = header_act.index(u_col)+1
                    ws_act.update_cell(row_idx_act, i_u, st.session_state["name"])
                    # timestamp
                    t_col = f"{col}_timestamp"; i_t = header_act.index(t_col)+1
                    ts = datetime.now().isoformat(sep=" ",timespec="seconds")
                    ws_act.update_cell(row_idx_act, i_t, ts)
                except Exception as e:
                    errs.append((col,str(e)))
            if errs:
                for c,msg in errs: st.error(f"{c}: {msg}")
            else:
                st.success("✅ Aprobación actualizada!")
                # refrescar
                df_act = pd.DataFrame(ws_act.get_all_records())
                fila_act = df_act.loc[df_act["Id_Actividad"]==id_act].iloc[0]

# 2) CAMPUS (editar)
pasos_campus = [
    ("C_ArmadoAula","Armado Aula"),
    ("C_Matriculacion","Matriculación participantes"),
    ("C_AperturaCurso","Apertura Curso"),
    ("C_CierreCurso","Cierre Curso"),
    ("C_AsistenciaEvaluacion","Entrega Notas y Asistencia"),
]
with st.expander("🛠️ Editar CAMPUS"):
    with st.form("form_campus"):
        cambios = []
        for c,label in pasos_campus:
            val = bool(fila_seg[c])
            chk = st.checkbox(label, value=val, disabled=val, key=f"fc_{c}")
            if chk and not val:
                cambios.append(c)
        if st.form_submit_button("💾 Actualizar CAMPUS"):
            errs=[]
            for col in cambios:
                try:
                    i_col = header_seg.index(col)+1
                    ws_seg.update_cell(row_seg, i_col, True)
                    u_col = f"{col}_user"; i_u = header_seg.index(u_col)+1
                    ws_seg.update_cell(row_seg, i_u, st.session_state["name"])
                    t_col = f"{col}_timestamp"; i_t = header_seg.index(t_col)+1
                    ts = datetime.now().isoformat(sep=" ",timespec="seconds")
                    ws_seg.update_cell(row_seg, i_t, ts)
                except Exception as e:
                    errs.append((col,str(e)))
            if errs:
                for c,msg in errs: st.error(f"{c}: {msg}")
            else:
                st.success("✅ Campus actualizado!")
                df_seg = pd.DataFrame(ws_seg.get_all_records())
                fila_seg = df_seg.loc[df_seg["Id_Comision"]==comision].iloc[0]

# 3) DICTADO COMISIÓN (editar)
pasos_dictado = [
    ("D_Difusion","Difusión"),
    ("D_AsignacionVacantes","Asignación Vacantes"),
    ("D_Cursada","Cursada"),
    ("D_AsistenciaEvaluacion","Asistencia y Evaluación"),
    ("D_CreditosSAI","Créditos SAI"),
    ("D_Liquidacion","Liquidación"),
]
with st.expander("🛠️ Editar DICTADO COMISIÓN"):
    with st.form("form_dictado"):
        cambios = []
        for c,label in pasos_dictado:
            val = bool(fila_seg[c])
            chk = st.checkbox(label, value=val, disabled=val, key=f"fd_{c}")
            if chk and not val:
                cambios.append(c)
        if st.form_submit_button("💾 Actualizar DICTADO"):
            errs=[]
            for col in cambios:
                try:
                    i_col = header_seg.index(col)+1
                    ws_seg.update_cell(row_seg, i_col, True)
                    u_col = f"{col}_user"; i_u = header_seg.index(u_col)+1
                    ws_seg.update_cell(row_seg, i_u, st.session_state["name"])
                    t_col = f"{col}_timestamp"; i_t = header_seg.index(t_col)+1
                    ts = datetime.now().isoformat(sep=" ",timespec="seconds")
                    ws_seg.update_cell(row_seg, i_t, ts)
                except Exception as e:
                    errs.append((col,str(e)))
            if errs:
                for c,msg in errs: st.error(f"{c}: {msg}")
            else:
                st.success("✅ Dictado actualizado!")
                df_seg = pd.DataFrame(ws_seg.get_all_records())
                fila_seg = df_seg.loc[df_seg["Id_Comision"]==comision].iloc[0]

# ---- STEPPER DINÁMICO DE COMISIÓN ----
st.markdown("---")
st.markdown("## 📊 Avance de Comisión")
for proc, pasos in [("CAMPUS", pasos_campus), ("DICTADO COMISIÓN", pasos_dictado)]:
    bools = [bool(fila_seg[c]) for c,_ in pasos]
    idx   = len(bools) if all(bools) else next(i for i,v in enumerate(bools) if not v)
    fig = go.Figure(); x=list(range(len(pasos))); y=1
    for i in range(len(pasos)-1):
        clr = col_ok if i<idx else col_ng
        fig.add_trace(go.Scatter(x=[x[i],x[i+1]],y=[y,y], mode="lines",
                                 line=dict(color=clr,width=8),showlegend=False))
    for i,(c,label) in enumerate(pasos):
        clr,ic = (
            (col_ok,   icono["finalizado"]) if i<idx else
            (col_now,  icono["actual"])     if i==idx else
            (col_ng,   icono["pendiente"])
        )
        user = fila_seg.get(f"{c}_user",""); ts = fila_seg.get(f"{c}_timestamp","")
        hover = f"{label}<br>Por: {user}<br>El: {ts}"
        fig.add_trace(go.Scatter(x=[x[i]],y=[y],mode="markers+text",
                                 marker=dict(size=45,color=clr),
                                 text=[ic],textposition="middle center",
                                 textfont=dict(color="white",size=18),
                                 hovertext=[hover],hoverinfo="text",showlegend=False))
        fig.add_trace(go.Scatter(x=[x[i]],y=[y-0.15],mode="text",
                                 text=[label],textposition="bottom center",
                                 textfont=dict(color="white",size=12),showlegend=False))
    fig.update_layout(
        title=dict(text=f"🔹 {proc}",x=0.01,xanchor="left",font=dict(size=16)),
        xaxis=dict(showgrid=False,zeroline=False,showticklabels=False),
        yaxis=dict(showgrid=False,zeroline=False,showticklabels=False,range=[0.3,1.2]),
        height=180, margin=dict(l=20,r=20,t=30,b=0)
    )
    st.plotly_chart(fig)


