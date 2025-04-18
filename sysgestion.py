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

# Constante para evitar 429
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
# 2) CACHE DE DATOS
# ────────────────────────────────────────────────
@st.cache_data(ttl=60)
def cargar_datos():
    def _cargar():
        with get_global_lock():
            hoja = get_sheet()
            names = ["actividades","comisiones","seguimiento"]
            data = {}
            for n in names:
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

# Cargar config y auth
with open("config.yaml") as f:
    config = yaml.load(f,SafeLoader)
authenticator = stauth.Authenticate(
    credentials=config["credentials"],
    cookie_name=config["cookie"]["name"],
    cookie_key=config["cookie"]["key"],
    cookie_expiry_days=config["cookie"]["expiry_days"]
)
authenticator.login()
if not st.session_state.get("authentication_status"):
    if st.session_state.get("authentication_status") is False:
        st.error("❌ Usuario o contraseña incorrectos.")
    else:
        st.warning("🔒 Ingresá tus credenciales.")
    st.stop()
# Auth ok
authenticator.logout("Cerrar sesión","sidebar")
st.sidebar.success(f"Hola, {st.session_state['name']}")
st.markdown("<h1 style='font-size:30px;color:white;'>Gestión Capacitación DCYCP</h1>",unsafe_allow_html=True)
username = st.session_state.get("username")
role = config["credentials"]["usernames"].get(username,{}).get("role","INVITADO")
perms = PERMISOS.get(role,PERMISOS["INVITADO"])

# Carga datos
try:
    sh,df_act,df_com,df_seg = None, *cargar_datos()
    sh = operacion_segura(get_sheet)
    if df_act is None: st.stop()
    df_comp = df_com.merge(df_act[["Id_Actividad","NombreActividad"]],on="Id_Actividad").merge(df_seg,on="Id_Comision")
except Exception as e:
    st.error(f"Error crítico: {e}")
    st.stop()

# Selecciones
cursos = df_act["NombreActividad"].unique().tolist()
curso = st.selectbox("Seleccioná un Curso:",cursos)
if f"comisiones_{curso}" not in st.session_state:
    st.session_state[f"comisiones_{curso}"] = df_comp[df_comp["NombreActividad"]==curso]["Id_Comision"].unique().tolist()
comision = st.selectbox("Seleccioná una Comisión:",st.session_state[f"comisiones_{curso}"])
# Filas
try:
    id_act = df_act[df_act["NombreActividad"]==curso]["Id_Actividad"].iloc[0]
    fila_act = df_act[df_act["Id_Actividad"]==id_act].iloc[0]
    fila_seg = df_seg[df_seg["Id_Comision"]==comision].iloc[0]
except:
    st.error("No hay datos para esa selección.")
    st.stop()
# Hojas\	ws_act = operacion_segura(lambda: sh.worksheet("actividades"))
header_act = operacion_segura(lambda: ws_act.row_values(1))
row_idx_act = operacion_segura(lambda: ws_act.find(str(id_act))).row
ws_seg = operacion_segura(lambda: sh.worksheet("seguimiento"))
header_seg = operacion_segura(lambda: ws_seg.row_values(1))
row_idx_seg = operacion_segura(lambda: ws_seg.find(str(comision))).row

# Estilos
color_ok="#4DB6AC";color_now="#FF8A65";color_noe="#D3D3D3"
icono={"finalizado":"✓","actual":"⏳","pendiente":"○"}

# Loop procesos
try:
    for proc,pasos in PROCESOS.items():
        if proc not in perms["view"]: continue
        # init estado tiempo
        if f"temp_{proc}" not in st.session_state: st.session_state[f"temp_{proc}"]=[]
        if "last_update" not in st.session_state: st.session_state["last_update"]=0.0
        # fuente
        src = fila_act if proc=="APROBACION" else fila_seg
        ws,header,row = (ws_act,header_act,row_idx_act) if proc=="APROBACION" else (ws_seg,header_seg,row_idx_seg)
        # progreso
        b = [bool(src[c]) or c in st.session_state[f"temp_{proc}"] for c,_ in pasos]
        idx = len(b) if all(b) else next(i for i,v in enumerate(b) if not v)
        # graficar
        fig=go.Figure();X=list(range(len(pasos)));Y=1
        for i in range(len(pasos)-1):cl=color_ok if i<idx else color_noe;fig.add_trace(go.Scatter(x=[X[i],X[i+1]],y=[Y,Y],mode="lines",line=dict(color=cl,width=8),showlegend=False))
        for i,(c,l) in enumerate(pasos):
            if c in st.session_state[f"temp_{proc}"] or i<idx:cl,ic=color_ok,icono["finalizado"]
            elif i==idx:cl,ic=color_now,icono["actual"]
            else:cl,ic=color_noe,icono["pendiente"]
            u=src.get(f"{c}_user","");ts=src.get(f"{c}_timestamp","")
            hover=f"{l}<br>Por: {u}<br>El: {ts}"
            fig.add_trace(go.Scatter(x=[X[i]],y=[Y],mode="markers+text",marker=dict(size=45,color=cl),text=[ic],textposition="middle center",textfont=dict(color="white",size=18),hovertext=[hover],hoverinfo="text",showlegend=False))
            fig.add_trace(go.Scatter(x=[X[i]],y=[Y-0.15],mode="text",text=[l],textposition="bottom center",textfont=dict(color="white",size=12),showlegend=False))
        fig.update_layout(title=dict(text=f"🔹 {proc}",x=0.01,xanchor="left",font=dict(size=16)),xaxis=dict(showgrid=False,zeroline=False,showticklabels=False),yaxis=dict(showgrid=False,zeroline=False,showticklabels=False,range=[0.3,1.2]),height=180,margin=dict(l=20,r=20,t=30,b=0))
        st.plotly_chart(fig)
        # editar
        if proc in perms["edit"]:
            with st.expander(f"🛠️ Editar {proc}"):
                with st.form(f"form_{proc}_{id_act}_{comision}"):
                    cambios=[]
                    for c,l in pasos:
                        est=bool(src[c]) or c in st.session_state[f"temp_{proc}"]
                        chk=st.checkbox(l,value=est,key=f"chk_{proc}_{c}")
                        if chk and not est: cambios.append(c)
                    sub=st.form_submit_button(f"💾 Actualizar {proc}")
                    if sub:
                        now=time.time()
                        if now-st.session_state["last_update"]<t_WAIT_SECONDS:
                            st.warning("⏳ Aguardá unos segundos antes del próximo cambio.")
                        else:
                            validos=[];invalidos=[]
                            for c in cambios:
                                j=[x for x,_ in pasos].index(c)
                                if all(bool(src[pasos[k][0]]) or pasos[k][0] in st.session_state[f"temp_{proc}"] for k in range(j)): validos.append(c)
                                else: invalidos.append(c)
                            if invalidos:
                                nombres=[pasos[[x for x,_ in pasos].index(x)][1] for x in invalidos]
                                st.warning(f"No podés completar {', '.join(nombres)} antes de los anteriores.")
                            if validos:
                                st.session_state[f"temp_{proc}"].extend(validos)
                                st.session_state["last_update"]=now
                                try:
                                    with st.spinner(f"🔄 Sincronizando {len(validos)} paso(s)..."):
                                        ts_iso=datetime.now().isoformat(sep=" ",timespec="seconds")
                                        reqs=[]
                                        for c in validos:
                                            i_c=header.index(c)+1
                                            reqs.append({'updateCells':{'range':{'sheetId':ws.id,'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':i_c-1,'endColumnIndex':i_c},'rows':[{'values':[{'userEnteredValue':{'boolValue':True}}]}],'fields':'userEnteredValue'}})
                                            uc=f"{c}_user";i_u=header.index(uc)+1
                                            reqs.append({'updateCells':{'range':{'sheetId':ws.id,'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':i_u-1,'endColumnIndex':i_u},'rows':[{'values':[{'userEnteredValue':{'stringValue':st.session_state['name']}}]}],'fields':'userEnteredValue'}})
                                            tc=f"{c}_timestamp";i_t=header.index(tc)+1
                                            reqs.append({'updateCells':{'range':{'sheetId':ws.id,'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':i_t-1,'endColumnIndex':i_t},'rows':[{'values':[{'userEnteredValue':{'stringValue':ts_iso}}]}],'fields':'userEnteredValue'}})
                                        for i in range(0,len(reqs),30):
                                            operacion_segura(lambda: ws.spreadsheet.batch_update({'requests':reqs[i:i+30]}))
                                            if i+30<len(reqs): time.sleep(1)
                                    # Recargar datos después de 1 segundo y rerun
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al sincronizar: {e}")
                                    st.session_state[f"temp_{proc}"]=[]
        else:
            if proc in perms["view"]:
                st.info(f"🔒 No tenés permisos para editar {proc}.")
except Exception as e:
    st.error(f"Error inesperado: {e}")
    st.stop()

# Ya manejamos auth arriba, no hay else final
