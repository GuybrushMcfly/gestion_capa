import threading
import json
from datetime import datetime
import time
import random
import gspread
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from google.oauth2.service_account import Credentials
from yaml.loader import SafeLoader
from gspread.exceptions import APIError

# ---- CONFIGURACIÓN DE PÁGINA ----
st.set_page_config(page_title="Gestión Capacitación DCYCP", layout="wide")
st.sidebar.image("logo-cap.png", use_container_width=True)
modo = st.get_option("theme.base")
color_texto = "#000000" if modo == "light" else "#FFFFFF"

# Tiempo mínimo entre actualizaciones para evitar 429 segundos
t_WAIT_SECONDS = 5

# ────────────────────────────────────────────────
# 1) FUNCIONES MEJORADAS CON MANEJO DE ERRORES
# ────────────────────────────────────────────────
@st.cache_resource
def get_global_lock():
    return threading.Lock()

def operacion_segura(operacion, max_reintentos=3, delay_base=1):
    for intento in range(max_reintentos):
        try:
            return operacion()
        except APIError:
            if intento == max_reintentos - 1:
                raise
            espera = delay_base * (2 ** intento) + random.uniform(0, 0.5)
            time.sleep(espera)

@st.cache_resource
def get_sheet():
    def _get_sheet():
        with get_global_lock():
            creds_dict = json.loads(st.secrets["GOOGLE_CREDS"])
            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            return gspread.authorize(creds).open_by_key(
                "1uYHnALX3TCaSzqJJFESOf8OpiaxKbLFYAQdcKFqbGrk"
            )
    return operacion_segura(_get_sheet)

# ────────────────────────────────────────────────
# 2) CACHE DE DATOS CON REINTENTOS
# ────────────────────────────────────────────────
@st.cache_data(ttl=60)
def cargar_datos():
    def _cargar():
        with get_global_lock():
            hoja = get_sheet()
            hojas = ["actividades","comisiones","seguimiento"]
            data = {}
            for n in hojas:
                ws = operacion_segura(lambda: hoja.worksheet(n))
                data[n] = operacion_segura(lambda: ws.get_all_records())
            return (
                pd.DataFrame(data["actividades"]),
                pd.DataFrame(data["comisiones"]),
                pd.DataFrame(data["seguimiento"])
            )
    try:
        return operacion_segura(_cargar)
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        return None, None, None

# ────────────────────────────────────────────────
# 3) PASOS Y PERMISOS
# ────────────────────────────────────────────────
pasos_act = [
    ("A_Diseño","Diseño"),
    ("A_AutorizacionINAP","Autorización INAP"),
    ("A_CargaSAI","Carga SAI"),
    ("A_TramitacionExpediente","Tramitación Expediente"),
    ("A_DictamenINAP","Dictamen INAP"),
]
pasos_campus = [
    ("C_ArmadoAula","Armado Aula"),
    ("C_Matriculacion","Matriculación participantes"),
    ("C_AperturaCurso","Apertura Curso"),
    ("C_CierreCurso","Cierre Curso"),
    ("C_AsistenciaEvaluacion","Entrega Notas y Asistencia"),
]
pasos_dictado = [
    ("D_Difusion","Difusión"),
    ("D_AsignacionVacantes","Asignación Vacantes"),
    ("D_Cursada","Cursada"),
    ("D_AsistenciaEvaluacion","Asistencia y Evaluación"),
    ("D_CreditosSAI","Créditos SAI"),
    ("D_Liquidacion","Liquidación"),
]
PROCESOS = {"APROBACION":pasos_act,"CAMPUS":pasos_campus,"DICTADO":pasos_dictado}
PERMISOS = {
    "ADMIN":   {"view":set(PROCESOS),"edit":set(PROCESOS)},
    "CAMPUS":  {"view":{"CAMPUS","DICTADO"},"edit":{"CAMPUS"}},
    "DISEÑO":  {"view":{"APROBACION"},"edit":{"APROBACION"}},
    "DICTADO": {"view":set(PROCESOS),"edit":{"DICTADO"}},
    "INVITADO":{"view":set(PROCESOS),"edit":set()},
}

# ---- CARGAR CONFIGURACIÓN Y AUTENTICACIÓN ----
with open("config.yaml") as f:
    config = yaml.load(f, SafeLoader)
authenticator = stauth.Authenticate(
    credentials=config["credentials"],
    cookie_name=config["cookie"]["name"],
    cookie_key=config["cookie"]["key"],
    cookie_expiry_days=config["cookie"]["expiry_days"]
)
authenticator.login()
if not st.session_state.get("authentication_status"):
    st.error("❌ Usuario/contraseña incorrectos.")
    st.stop()
# usuario ok
authenticator.logout("Cerrar sesión","sidebar")
st.sidebar.success(f"Hola, {st.session_state['name']}")
st.markdown("<h1 style='font-size:30px; color:white;'>Gestión Capacitación DCYCP</h1>",unsafe_allow_html=True)
username = st.session_state.get("username")
role = config["credentials"]["usernames"].get(username,{}).get("role","INVITADO")
perms = PERMISOS.get(role, PERMISOS["INVITADO"])

# ────────────────────────────────────────────────
# 4) CARGA DE DATOS
# ────────────────────────────────────────────────
try:
    sh = operacion_segura(get_sheet)
    df_act, df_com, df_seg = cargar_datos()
    if df_act is None:
        st.stop()
    df_comp = (
        df_com
        .merge(df_act[["Id_Actividad","NombreActividad"]], on="Id_Actividad", how="left")
        .merge(df_seg, on="Id_Comision", how="left")
    )
except Exception as e:
    st.error(f"Error crítico al cargar datos: {e}")
    st.stop()

# ────────────────────────────────────────────────
# 5) INTERFAZ DE USUARIO
# ────────────────────────────────────────────────
cursos = df_act["NombreActividad"].unique().tolist()
curso = st.selectbox("Seleccioná un Curso:", cursos)
key = f"comisiones_{curso}"
if key not in st.session_state:
    st.session_state[key] = df_comp[df_comp["NombreActividad"]==curso]["Id_Comision"].unique().tolist()
comision = st.selectbox("Seleccioná una Comisión:", st.session_state[key])
try:
    id_act = df_act[df_act["NombreActividad"]==curso]["Id_Actividad"].iloc[0]
    fila_act = df_act[df_act["Id_Actividad"]==id_act].iloc[0]
    fila_seg = df_seg[df_seg["Id_Comision"]==comision].iloc[0]
except:
    st.error("No hay datos para esa selección.")
    st.stop()

# obtener hojas y metadatos
ws_act = operacion_segura(lambda: sh.worksheet("actividades"))
header_act = operacion_segura(lambda: ws_act.row_values(1))
row_act = operacion_segura(lambda: ws_act.find(str(id_act))).row
ws_seg = operacion_segura(lambda: sh.worksheet("seguimiento"))
header_seg = operacion_segura(lambda: ws_seg.row_values(1))
row_seg = operacion_segura(lambda: ws_seg.find(str(comision))).row

# estilos e íconos
col_ok = "#4DB6AC"
col_now = "#FF8A65"
col_no  = "#D3D3D3"
icono={"finalizado":"✓","actual":"⏳","pendiente":"○"}

# ────────────────────────────────────────────────
# 6) VISUALIZACIÓN Y EDICIÓN DE PROCESOS
# ────────────────────────────────────────────────
for proc,pasos in PROCESOS.items():
    if proc not in perms["view"]:
        continue

    temp_key = f"temp_{proc}"
    if temp_key not in st.session_state:
        st.session_state[temp_key] = []
    if "last_update" not in st.session_state:
        st.session_state["last_update"] = 0.0

    src = fila_act if proc=="APROBACION" else fila_seg
    ws, header, row = (
        (ws_act, header_act, row_act) if proc=="APROBACION"
        else (ws_seg, header_seg, row_seg)
    )

    # calcular índice
    bools = [bool(src[c]) or c in st.session_state[temp_key] for c,_ in pasos]
    idx = len(bools) if all(bools) else next(i for i,v in enumerate(bools) if not v)

    # graficar progreso
    xs = list(range(len(pasos)))
    fig = go.Figure()
    for i in range(len(pasos)-1):
        clr = col_ok if i<idx else col_no
        fig.add_trace(go.Scatter(x=[xs[i],xs[i+1]], y=[1,1], mode="lines", line=dict(color=clr, width=8), showlegend=False))
    for i,(c,lbl) in enumerate(pasos):
        if c in st.session_state[temp_key] or i<idx:
            clr, ic = col_ok, icono["finalizado"]
        elif i==idx:
            clr, ic = col_now, icono["actual"]
        else:
            clr, ic = col_no, icono["pendiente"]
        hover = f"{lbl}<br>Por: {src.get(c+'_user','')}<br>El: {src.get(c+'_timestamp','')}"
        fig.add_trace(go.Scatter(x=[xs[i]], y=[1], mode="markers+text", marker=dict(color=clr, size=45), text=[ic], textposition="middle center", hovertext=[hover], hoverinfo="text", showlegend=False))
        fig.add_trace(go.Scatter(x=[xs[i]], y=[0.85], mode="text", text=[lbl], textposition="bottom center", showlegend=False))
    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False, range=[0.3,1.2]), height=180, margin=dict(l=20,r=20,t=30,b=0), title=dict(text=f"🔹 {proc}", x=0.01, xanchor="left"))
    st.plotly_chart(fig)

    # edición
    if proc in perms["edit"]:
        with st.expander(f"🛠️ Editar {proc}"):
            with st.form(f"form_{proc}_{id_act}_{comision}"):
                cambios=[]
                for c,lbl in pasos:
                    est = bool(src[c]) or c in st.session_state[temp_key]
                    chk = st.checkbox(lbl, value=est, key=f"chk_{proc}_{c}")
                    if chk and not est:
                        cambios.append(c)
                sub = st.form_submit_button(f"💾 Actualizar {proc}")
                if sub:
                    now = time.time()
                    if now - st.session_state["last_update"] < t_WAIT_SECONDS:
                        st.warning(f"⏳ Aguardá {int(t_WAIT_SECONDS - (now - st.session_state['last_update']))} seg.")
                    else:
                        validos=[]
                        for c in cambios:
                            j=[x for x,_ in pasos].index(c)
                            if all(bool(src[pasos[k][0]]) or pasos[k][0] in st.session_state[temp_key] for k in range(j)):
                                validos.append(c)
                        if not validos:
                            st.info("No hay cambios válidos o en orden.")
                        else:
                            st.session_state[temp_key].extend(validos)
                            st.session_state["last_update"] = now
                            try:
                                with st.spinner(f"🔄 Sincronizando {len(validos)} paso(s)..."):
                                    ts_iso=datetime.now().isoformat(sep=" ", timespec="seconds")
                                    reqs=[]
                                    for c in validos:
                                        i_c=header.index(c)+1
                                        reqs.append({'updateCells':{'range':{'sheetId':ws.id,'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':i_c-1,'endColumnIndex':i_c},'rows':[{'values':[{'userEnteredValue':{'boolValue':True}}]}],'fields':'userEnteredValue'}})
                                        ucol, tcol = f"{c}_user", f"{c}_timestamp"
                                        i_u, i_t = header.index(ucol)+1, header.index(tcol)+1
                                        reqs.extend([
                                            {'updateCells':{'range':{'sheetId':ws.id,'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':i_u-1,'endColumnIndex':i_u},'rows':[{'values':[{'userEnteredValue':{'stringValue':st.session_state['name']}}]}],'fields':'userEnteredValue'}},
                                            {'updateCells':{'range':{'sheetId':ws.id,'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':i_t-1,'endColumnIndex':i_t},'rows':[{'values':[{'userEnteredValue':{'stringValue':ts_iso}}]}],'fields':'userEnteredValue'}}
                                        ])
                                    for i in range(0,len(reqs),30):
                                        operacion_segura(lambda: ws.spreadsheet.batch_update({'requests':reqs[i:i+30]}))
                                        if i+30<len(reqs): time.sleep(1)
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error de sincronización: {e}")
                                st.session_state[temp_key] = []
    else:
        st.info(f"🔒 Sin permisos para editar {proc}.")
