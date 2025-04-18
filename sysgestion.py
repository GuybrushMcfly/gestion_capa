import threading
import json
from datetime import datetime
import time
import gspread
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from google.oauth2.service_account import Credentials
from yaml.loader import SafeLoader

# ---- CONFIGURACIÓN DE PÁGINA ----
st.set_page_config(page_title="Gestión Capacitación DCYCP", layout="wide")
st.sidebar.image("logo-cap.png", use_container_width=True)
modo = st.get_option("theme.base")
color_texto = "#000000" if modo == "light" else "#FFFFFF"

# ────────────────────────────────────────────────
# 1) GLOBAL LOCK + CACHE DE CONEXIÓN A GOOGLE SHEETS
# ────────────────────────────────────────────────
@st.cache_resource
def get_global_lock():
    return threading.Lock()

@st.cache_resource
def get_sheet():
    with get_global_lock():
        creds_dict = json.loads(st.secrets["GOOGLE_CREDS"])
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        gc = gspread.authorize(creds)
        return gc.open_by_key("1uYHnALX3TCaSzqJJFESOf8OpiaxKbLFYAQdcKFqbGrk")

# ────────────────────────────────────────────────
# 2) CACHE DE DATOS (1 minuto)                  
# ────────────────────────────────────────────────
@st.cache_data(ttl=60)
def cargar_datos():
    with get_global_lock():
        try:
            hoja = get_sheet()
            # Leer todas las hojas en una sola operación
            worksheets = hoja.worksheets()
            data = {ws.title: ws.get_all_records() for ws in worksheets if ws.title in ["actividades", "comisiones", "seguimiento"]}
            
            df_actividades = pd.DataFrame(data["actividades"])
            df_comisiones = pd.DataFrame(data["comisiones"])
            df_seguimiento = pd.DataFrame(data["seguimiento"])
            return df_actividades, df_comisiones, df_seguimiento
        except Exception as e:
            st.error(f"Error al cargar datos: {e}")
            return None, None, None

# ────────────────────────────────────────────────
# 3) DEFINICIÓN DE PASOS Y PERMISOS
# ────────────────────────────────────────────────
pasos_act = [
    ("A_Diseño",                "Diseño"),
    ("A_AutorizacionINAP",      "Autorización INAP"),
    ("A_CargaSAI",              "Carga SAI"),
    ("A_TramitacionExpediente", "Tramitación Expediente"),
    ("A_DictamenINAP",          "Dictamen INAP"),
]

pasos_campus = [
    ("C_ArmadoAula",           "Armado Aula"),
    ("C_Matriculacion",        "Matriculación participantes"),
    ("C_AperturaCurso",        "Apertura Curso"),
    ("C_CierreCurso",          "Cierre Curso"),
    ("C_AsistenciaEvaluacion", "Entrega Notas y Asistencia"),
]

pasos_dictado = [
    ("D_Difusion",               "Difusión"),
    ("D_AsignacionVacantes",     "Asignación Vacantes"),
    ("D_Cursada",                "Cursada"),
    ("D_AsistenciaEvaluacion",   "Asistencia y Evaluación"),
    ("D_CreditosSAI",            "Créditos SAI"),
    ("D_Liquidacion",            "Liquidación"),
]

PROCESOS = {
    "APROBACION": pasos_act,
    "CAMPUS":    pasos_campus,
    "DICTADO":   pasos_dictado,
}

PERMISOS = {
    "ADMIN":    {"view": set(PROCESOS),                    "edit": set(PROCESOS)},
    "CAMPUS":   {"view": {"CAMPUS", "DICTADO"},            "edit": {"CAMPUS"}},
    "DISEÑO":   {"view": {"APROBACION"},                   "edit": {"APROBACION"}},
    "DICTADO":  {"view": set(PROCESOS),                    "edit": {"DICTADO"}},
    "INVITADO": {"view": set(PROCESOS),                    "edit": set()},
}

# ---- CARGAR CONFIGURACIÓN DE USUARIOS ----
with open("config.yaml") as file:
    config = yaml.load(file, Loader=SafeLoader)

# ---- AUTENTICACIÓN ----
authenticator = stauth.Authenticate(
    credentials=config["credentials"],
    cookie_name=config["cookie"]["name"],
    cookie_key=config["cookie"]["key"],
    cookie_expiry_days=config["cookie"]["expiry_days"]
)
authenticator.login()

if st.session_state.get("authentication_status"):
    authenticator.logout("Cerrar sesión", "sidebar")
    st.sidebar.success(f"Hola, {st.session_state['name']}")
    st.markdown("<h1 style='font-size:30px; color:white;'>Gestión Capacitación DCYCP</h1>",
                unsafe_allow_html=True)

    username = st.session_state.get("username")
    user_cfg = config["credentials"]["usernames"].get(username, {})
    role = user_cfg.get("role", "INVITADO")
    perms = PERMISOS.get(role, PERMISOS["INVITADO"])

    # ────────────────────────────────────────────────
    # 4) CARGA DE DATOS DESDE GOOGLE SHEETS
    # ────────────────────────────────────────────────
    sh = get_sheet()
    df_actividades, df_comisiones, df_seguimiento = cargar_datos()
    if df_actividades is None:
        st.error("No se pudieron cargar los datos. Por favor, intenta de nuevo.")
        st.stop()
    
    df_completo = (
        df_comisiones
        .merge(df_actividades[["Id_Actividad", "NombreActividad"]], on="Id_Actividad", how="left")
        .merge(df_seguimiento, on="Id_Comision", how="left")
    )

    # ────────────────────────────────────────────────
    # 5) SELECCIÓN DE CURSO Y COMISIÓN
    # ────────────────────────────────────────────────
    curso = st.selectbox("Seleccioná un Curso:", df_actividades["NombreActividad"].unique())
    coms = df_completo.loc[df_completo["NombreActividad"] == curso, "Id_Comision"].unique().tolist()
    comision = st.selectbox("Seleccioná una Comisión:", coms)

    id_act = df_actividades.loc[df_actividades["NombreActividad"] == curso, "Id_Actividad"].iloc[0]
    fila_act = df_actividades.loc[df_actividades["Id_Actividad"] == id_act].iloc[0]
    fila_seg = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]

    ws_act = sh.worksheet("actividades")
    header_act = ws_act.row_values(1)
    row_idx_act = ws_act.find(str(id_act)).row

    ws_seg = sh.worksheet("seguimiento")
    header_seg = ws_seg.row_values(1)
    row_idx_seg = ws_seg.find(str(comision)).row

    # Colores e íconos
    color_completado = "#4DB6AC"
    color_actual = "#FF8A65"
    color_pendiente = "#D3D3D3"
    icono = {"finalizado":"⚪","actual":"⏳","pendiente":"⚪"}

    # ────────────────────────────────────────────────
    # 6) ITERAR SOBRE CADA PROCESO (vista + edición condicional)
    # ────────────────────────────────────────────────
    for proc_name, pasos in PROCESOS.items():
        if proc_name not in perms["view"]:
            continue

        # Usar estado de sesión para manejar cambios temporales
        if f"temp_{proc_name}" not in st.session_state:
            st.session_state[f"temp_{proc_name}"] = None

        # Calcular índice actual
        source_row = fila_act if proc_name == "APROBACION" else fila_seg
        bools = [bool(source_row[col]) for col, _ in pasos]
        idx = len(bools) if all(bools) else next(i for i,v in enumerate(bools) if not v)

        # Crear figura
        fig = go.Figure()
        x, y = list(range(len(pasos))), 1

        # Líneas
        for i in range(len(pasos)-1):
            clr = color_completado if i < idx else color_pendiente
            fig.add_trace(go.Scatter(
                x=[x[i], x[i+1]], y=[y, y], mode="lines",
                line=dict(color=clr, width=8), showlegend=False
            ))

        # Puntos + iconos
        for i,(col,label) in enumerate(pasos):
            # Verificar si hay cambios temporales en el estado de sesión
            if st.session_state[f"temp_{proc_name}"] and col in st.session_state[f"temp_{proc_name}"]:
                clr, ic = color_completado, icono["finalizado"]
            elif i < idx:
                clr, ic = color_completado, icono["finalizado"]
            elif i == idx:
                clr, ic = color_actual, icono["actual"]
            else:
                clr, ic = color_pendiente, icono["pendiente"]

            user = source_row.get(f"{col}_user","")
            ts = source_row.get(f"{col}_timestamp","")
            hover = f"{label}<br>Por: {user}<br>El: {ts}"

            fig.add_trace(go.Scatter(
                x=[x[i]], y=[y], mode="markers+text",
                marker=dict(size=45, color=clr),
                text=[ic], textposition="middle center",
                textfont=dict(color="white", size=18),
                hovertext=[hover], hoverinfo="text", showlegend=False
            ))
            fig.add_trace(go.Scatter(
                x=[x[i]], y=[y-0.15], mode="text",
                text=[label], textposition="bottom center",
                textfont=dict(color="white", size=12), showlegend=False
            ))

        fig.update_layout(
            title=dict(text=f"🔹 {proc_name}", x=0.01, xanchor="left", font=dict(size=16)),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.3,1.2]),
            height=180, margin=dict(l=20, r=20, t=30, b=0),
        )
        st.plotly_chart(fig)

        # 6.2) Edición (solo si tiene permiso de editar)
        if proc_name in perms["edit"]:
            with st.expander(f"🛠️ Editar {proc_name}"):
                form_key = f"form_{proc_name}_{id_act}_{comision}"
                with st.form(form_key):
                    cambios = []
                    for col, label in pasos:
                        marcado = bool(source_row[col])
                        chk = st.checkbox(
                            label,
                            value=marcado,
                            disabled=marcado,
                            key=f"chk_{proc_name}_{id_act if proc_name=='APROBACION' else comision}_{col}"
                        )
                        if chk and not marcado:
                            cambios.append(col)

                    submitted = st.form_submit_button(f"💾 Actualizar {proc_name}")
                    if submitted:
                        if not cambios:
                            st.warning("No seleccionaste ningún paso para actualizar.")
                        else:
                            # Guardar cambios temporales para mostrar inmediatamente
                            st.session_state[f"temp_{proc_name}"] = cambios
                            
                            try:
                                # Determinar hoja y header según proc
                                ws, hdr, ridx = (
                                    (ws_act, header_act, row_idx_act)
                                    if proc_name == "APROBACION"
                                    else (ws_seg, header_seg, row_idx_seg)
                                )
                                
                                # Preparar todas las actualizaciones
                                requests = []
                                now = datetime.now().isoformat(sep=" ", timespec="seconds")
                                
                                for col in cambios:
                                    # Actualizar el campo booleano
                                    idx_col = hdr.index(col) + 1
                                    requests.append({
                                        'updateCells': {
                                            'range': {
                                                'sheetId': ws.id,
                                                'startRowIndex': ridx-1,
                                                'endRowIndex': ridx,
                                                'startColumnIndex': idx_col-1,
                                                'endColumnIndex': idx_col
                                            },
                                            'rows': [{
                                                'values': [{'userEnteredValue': {'boolValue': True}}]
                                            }],
                                            'fields': 'userEnteredValue'
                                        }
                                    })
                                    
                                    # Actualizar usuario
                                    ucol = f"{col}_user"
                                    idx_u = hdr.index(ucol) + 1
                                    requests.append({
                                        'updateCells': {
                                            'range': {
                                                'sheetId': ws.id,
                                                'startRowIndex': ridx-1,
                                                'endRowIndex': ridx,
                                                'startColumnIndex': idx_u-1,
                                                'endColumnIndex': idx_u
                                            },
                                            'rows': [{
                                                'values': [{'userEnteredValue': {'stringValue': st.session_state["name"]}}]
                                            }],
                                            'fields': 'userEnteredValue'
                                        }
                                    })
                                    
                                    # Actualizar timestamp
                                    tcol = f"{col}_timestamp"
                                    idx_t = hdr.index(tcol) + 1
                                    requests.append({
                                        'updateCells': {
                                            'range': {
                                                'sheetId': ws.id,
                                                'startRowIndex': ridx-1,
                                                'endRowIndex': ridx,
                                                'startColumnIndex': idx_t-1,
                                                'endColumnIndex': idx_t
                                            },
                                            'rows': [{
                                                'values': [{'userEnteredValue': {'stringValue': now}}]
                                            }],
                                            'fields': 'userEnteredValue'
                                        }
                                    })
                                
                                # Ejecutar todas las actualizaciones en una sola llamada
                                if requests:
                                    # Dividir las solicitudes en lotes más pequeños si son muchas
                                    batch_size = 30  # Google permite hasta 60 solicitudes por lote
                                    for i in range(0, len(requests), batch_size):
                                        batch = requests[i:i + batch_size]
                                        ws.spreadsheet.batch_update({'requests': batch})
                                        if i + batch_size < len(requests):
                                            time.sleep(1)  # Pequeña pausa entre lotes
                                
                                st.success(f"✅ {proc_name} actualizado correctamente!")
                                
                                # Forzar recarga de datos después de 2 segundos
                                time.sleep(2)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Error al actualizar: {str(e)}")
                                # Limpiar cambios temporales si hay error
                                st.session_state[f"temp_{proc_name}"] = None
        else:
            if proc_name in perms["view"]:
                st.info(f"🔒 No tenés permisos para editar {proc_name}.")
else:
    if st.session_state.get("authentication_status") is False:
        st.error("❌ Usuario o contraseña incorrectos.")
    else:
        st.warning("🔒 Ingresá tus credenciales para acceder.")
    st.stop()
