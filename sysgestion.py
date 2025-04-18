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

# ────────────────────────────────────────────────
# 1) FUNCIONES MEJORADAS CON MANEJO DE ERRORES
# ────────────────────────────────────────────────
@st.cache_resource
def get_global_lock():
    return threading.Lock()

def operacion_segura(operacion, max_reintentos=3, delay_base=1):
    """Ejecuta operaciones con reintentos inteligentes"""
    for intento in range(max_reintentos):
        try:
            return operacion()
        except APIError as e:
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
            return gspread.authorize(creds).open_by_key("1uYHnALX3TCaSzqJJFESOf8OpiaxKbLFYAQdcKFqbGrk")
    
    return operacion_segura(_get_sheet)

# ────────────────────────────────────────────────
# 2) CACHE DE DATOS CON REINTENTOS
# ────────────────────────────────────────────────
@st.cache_data(ttl=60)
def cargar_datos():
    def _cargar_datos():
        with get_global_lock():
            try:
                hoja = get_sheet()
                hojas_necesarias = ["actividades", "comisiones", "seguimiento"]
                data = {}
                
                for hoja_nombre in hojas_necesarias:
                    ws = operacion_segura(lambda: hoja.worksheet(hoja_nombre))
                    data[hoja_nombre] = operacion_segura(lambda: ws.get_all_records())
                
                return (
                    pd.DataFrame(data["actividades"]),
                    pd.DataFrame(data["comisiones"]),
                    pd.DataFrame(data["seguimiento"])
                )
            except Exception as e:
                st.error(f"Error al cargar datos: {e}")
                return None, None, None
    
    return operacion_segura(_cargar_datos)

# ────────────────────────────────────────────────
# 3) DEFINICIÓN DE PASOS Y PERMISOS
# ────────────────────────────────────────────────
pasos_act = [
    ("A_Diseño", "Diseño"),
    ("A_AutorizacionINAP", "Autorización INAP"),
    ("A_CargaSAI", "Carga SAI"),
    ("A_TramitacionExpediente", "Tramitación Expediente"),
    ("A_DictamenINAP", "Dictamen INAP"),
]

pasos_campus = [
    ("C_ArmadoAula", "Armado Aula"),
    ("C_Matriculacion", "Matriculación participantes"),
    ("C_AperturaCurso", "Apertura Curso"),
    ("C_CierreCurso", "Cierre Curso"),
    ("C_AsistenciaEvaluacion", "Entrega Notas y Asistencia"),
]

pasos_dictado = [
    ("D_Difusion", "Difusión"),
    ("D_AsignacionVacantes", "Asignación Vacantes"),
    ("D_Cursada", "Cursada"),
    ("D_AsistenciaEvaluacion", "Asistencia y Evaluación"),
    ("D_CreditosSAI", "Créditos SAI"),
    ("D_Liquidacion", "Liquidación"),
]

PROCESOS = {
    "APROBACION": pasos_act,
    "CAMPUS": pasos_campus,
    "DICTADO": pasos_dictado,
}

PERMISOS = {
    "ADMIN": {"view": set(PROCESOS), "edit": set(PROCESOS)},
    "CAMPUS": {"view": {"CAMPUS", "DICTADO"}, "edit": {"CAMPUS"}},
    "DISEÑO": {"view": {"APROBACION"}, "edit": {"APROBACION"}},
    "DICTADO": {"view": set(PROCESOS), "edit": {"DICTADO"}},
    "INVITADO": {"view": set(PROCESOS), "edit": set()},
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
    st.markdown("<h1 style='font-size:30px; color:white;'>Gestión Capacitación DCYCP</h1>", unsafe_allow_html=True)

    username = st.session_state.get("username")
    user_cfg = config["credentials"]["usernames"].get(username, {})
    role = user_cfg.get("role", "INVITADO")
    perms = PERMISOS.get(role, PERMISOS["INVITADO"])

    # ────────────────────────────────────────────────
    # 4) CARGA DE DATOS
    # ────────────────────────────────────────────────
    try:
        sh = operacion_segura(get_sheet)
        df_actividades, df_comisiones, df_seguimiento = cargar_datos()
        
        if df_actividades is None or df_comisiones is None or df_seguimiento is None:
            st.error("No se pudieron cargar los datos. Por favor, intenta de nuevo.")
            st.stop()

        df_completo = (
            df_comisiones
            .merge(df_actividades[["Id_Actividad", "NombreActividad"]], on="Id_Actividad", how="left")
            .merge(df_seguimiento, on="Id_Comision", how="left")
        )
    except Exception as e:
        st.error(f"Error crítico al cargar datos: {str(e)}")
        st.stop()

    # ────────────────────────────────────────────────
    # 5) INTERFAZ DE USUARIO
    # ────────────────────────────────────────────────
    try:
        # Selección de curso
        cursos_disponibles = df_actividades["NombreActividad"].unique().tolist()
        curso = st.selectbox("Seleccioná un Curso:", cursos_disponibles)
        
        # Selección de comisión
        if f"comisiones_{curso}" not in st.session_state:
            st.session_state[f"comisiones_{curso}"] = df_completo.loc[
                df_completo["NombreActividad"] == curso, "Id_Comision"
            ].unique().tolist()
        
        coms = st.session_state[f"comisiones_{curso}"]
        comision = st.selectbox("Seleccioná una Comisión:", coms)

        # Obtener datos específicos
        try:
            id_act = df_actividades.loc[df_actividades["NombreActividad"] == curso, "Id_Actividad"].iloc[0]
            fila_act = df_actividades.loc[df_actividades["Id_Actividad"] == id_act].iloc[0]
            fila_seg = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]
        except IndexError as e:
            st.error("No se encontraron datos para la selección actual. Intenta con otra comisión.")
            st.stop()

        # Cargar hojas con reintentos
        try:
            ws_act = operacion_segura(lambda: sh.worksheet("actividades"))
            header_act = operacion_segura(lambda: ws_act.row_values(1))
            row_idx_act = operacion_segura(lambda: ws_act.find(str(id_act))).row

            ws_seg = operacion_segura(lambda: sh.worksheet("seguimiento"))
            header_seg = operacion_segura(lambda: ws_seg.row_values(1))
            row_idx_seg = operacion_segura(lambda: ws_seg.find(str(comision))).row
        except APIError as e:
            st.error("Error al acceder a Google Sheets. Espera un momento y recarga la página.")
            st.stop()
        except Exception as e:
            st.error(f"Error inesperado: {str(e)}")
            st.stop()

        # Configuración visual
        color_completado = "#4DB6AC"
        color_actual = "#FF8A65"
        color_pendiente = "#D3D3D3"
        icono = {"finalizado": "✓", "actual": "⏳", "pendiente": "○"}

        # ────────────────────────────────────────────────
        # 6) VISUALIZACIÓN Y EDICIÓN DE PROCESOS
        # ────────────────────────────────────────────────
        for proc_name, pasos in PROCESOS.items():
            if proc_name not in perms["view"]:
                continue

            # Estado temporal para cambios no confirmados
            if f"temp_{proc_name}" not in st.session_state:
                st.session_state[f"temp_{proc_name}"] = []

            # Datos fuente según el proceso
            source_row = fila_act if proc_name == "APROBACION" else fila_seg
            ws = ws_act if proc_name == "APROBACION" else ws_seg
            header = header_act if proc_name == "APROBACION" else header_seg
            row_idx = row_idx_act if proc_name == "APROBACION" else row_idx_seg

            # Calcular progreso actual
            bools = [bool(source_row[col]) or (col in st.session_state[f"temp_{proc_name}"]) for col, _ in pasos]
            idx = len(bools) if all(bools) else next((i for i, v in enumerate(bools) if not v), 0)

            # Crear gráfico de progreso
            fig = go.Figure()
            x, y = list(range(len(pasos))), 1

            # Líneas de conexión
            for i in range(len(pasos)-1):
                clr = color_completado if i < idx else color_pendiente
                fig.add_trace(go.Scatter(
                    x=[x[i], x[i+1]], y=[y, y], mode="lines",
                    line=dict(color=clr, width=8), showlegend=False
                ))

            # Marcadores de estado
            for i, (col, label) in enumerate(pasos):
                if col in st.session_state[f"temp_{proc_name}"]:
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

            # Panel de edición
            if proc_name in perms["edit"]:
                with st.expander(f"🛠️ Editar {proc_name}"):
                    form_key = f"form_{proc_name}_{id_act}_{comision}"
                    with st.form(form_key):
                        cambios = []
                        for col, label in pasos:
                            estado_actual = bool(source_row[col]) or (col in st.session_state[f"temp_{proc_name}"])
                            if not estado_actual:
                                if st.checkbox(label, key=f"chk_{proc_name}_{col}"):
                                    cambios.append(col)

                        submitted = st.form_submit_button(f"💾 Actualizar {proc_name}")
                        if submitted:
                            if not cambios:
                                st.warning("No seleccionaste ningún paso para actualizar.")
                            else:
                                # Actualización visual inmediata
                                st.session_state[f"temp_{proc_name}"].extend(cambios)
                                st.rerun()

                                # Operación en segundo plano
                                try:
                                    with st.spinner(f"🔄 Sincronizando {len(cambios)} paso(s) con la nube..."):
                                        # Preparar actualizaciones
                                        now = datetime.now().isoformat(sep=" ", timespec="seconds")
                                        requests = []
                                        
                                        for col in cambios:
                                            # Campo booleano
                                            idx_col = header.index(col) + 1
                                            requests.append({
                                                'updateCells': {
                                                    'range': {
                                                        'sheetId': ws.id,
                                                        'startRowIndex': row_idx-1,
                                                        'endRowIndex': row_idx,
                                                        'startColumnIndex': idx_col-1,
                                                        'endColumnIndex': idx_col
                                                    },
                                                    'rows': [{
                                                        'values': [{'userEnteredValue': {'boolValue': True}}]
                                                    }],
                                                    'fields': 'userEnteredValue'
                                                }
                                            })
                                            
                                            # Usuario
                                            ucol = f"{col}_user"
                                            idx_u = header.index(ucol) + 1
                                            requests.append({
                                                'updateCells': {
                                                    'range': {
                                                        'sheetId': ws.id,
                                                        'startRowIndex': row_idx-1,
                                                        'endRowIndex': row_idx,
                                                        'startColumnIndex': idx_u-1,
                                                        'endColumnIndex': idx_u
                                                    },
                                                    'rows': [{
                                                        'values': [{'userEnteredValue': {'stringValue': st.session_state["name"]}}]
                                                    }],
                                                    'fields': 'userEnteredValue'
                                                }
                                            })
                                            
                                            # Timestamp
                                            tcol = f"{col}_timestamp"
                                            idx_t = header.index(tcol) + 1
                                            requests.append({
                                                'updateCells': {
                                                    'range': {
                                                        'sheetId': ws.id,
                                                        'startRowIndex': row_idx-1,
                                                        'endRowIndex': row_idx,
                                                        'startColumnIndex': idx_t-1,
                                                        'endColumnIndex': idx_t
                                                    },
                                                    'rows': [{
                                                        'values': [{'userEnteredValue': {'stringValue': now}}]
                                                    }],
                                                    'fields': 'userEnteredValue'
                                                }
                                            })
                                        
                                        # Ejecutar en lotes
                                        batch_size = 30
                                        for i in range(0, len(requests), batch_size):
                                            operacion_segura(
                                                lambda: ws.spreadsheet.batch_update({'requests': requests[i:i+batch_size]})
                                            )
                                            if i + batch_size < len(requests):
                                                time.sleep(1)
                                        
                                        # Limpiar cambios temporales después de éxito
                                        st.session_state[f"temp_{proc_name}"] = []
                                        st.toast(f"✅ {proc_name} actualizado correctamente!", icon="✅")
                                        
                                        # Recargar datos después de 1 segundo
                                        time.sleep(1)
                                        st.rerun()
                                
                                except Exception as e:
                                    st.error(f"Error al sincronizar: {str(e)}")
                                    st.session_state[f"temp_{proc_name}"] = []
            else:
                if proc_name in perms["view"]:
                    st.info(f"🔒 No tenés permisos para editar {proc_name}.")

    except Exception as e:
        st.error(f"Error inesperado: {str(e)}")
        st.stop()

else:
    if st.session_state.get("authentication_status") is False:
        st.error("❌ Usuario o contraseña incorrectos.")
    else:
        st.warning("🔒 Ingresá tus credenciales para acceder.")
    st.stop()
