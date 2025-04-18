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

    cursos_disponibles = df_actividades["NombreActividad"].unique().tolist()
    curso = st.selectbox("Seleccioná un Curso:", cursos_disponibles)

    if f"comisiones_{curso}" not in st.session_state:
        st.session_state[f"comisiones_{curso}"] = df_completo.loc[
            df_completo["NombreActividad"] == curso, "Id_Comision"
        ].unique().tolist()

    coms = st.session_state[f"comisiones_{curso}"]
    comision = st.selectbox("Seleccioná una Comisión:", coms)

    try:
        id_act = df_actividades.loc[df_actividades["NombreActividad"] == curso, "Id_Actividad"].iloc[0]
        fila_act = df_actividades.loc[df_actividades["Id_Actividad"] == id_act].iloc[0]
        fila_seg = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]
    except IndexError as e:
        st.error("No se encontraron datos para la selección actual. Intenta con otra comisión.")
        st.stop()

    for proc_name, pasos in PROCESOS.items():
        if proc_name not in perms["view"]:
            continue

        st.markdown(f"### {proc_name}")
        key_base = f"chk_{proc_name}_{id_act}_{comision}"
        if key_base not in st.session_state:
            st.session_state[key_base] = {}
            for col, _ in pasos:
                valor_inicial = bool((fila_act if proc_name == "APROBACION" else fila_seg).get(col, False))
                st.session_state[key_base][col] = valor_inicial

        for i, (col, label) in enumerate(pasos):
            st.session_state[key_base][col] = st.checkbox(
                label,
                value=st.session_state[key_base][col],
                key=f"{key_base}_{col}"
            )

        if proc_name in perms["edit"]:
            if st.button(f"💾 Actualizar {proc_name}"):
                estado = st.session_state[key_base]
                for i in range(len(pasos)):
                    col = pasos[i][0]
                    if estado[col]:
                        anteriores = [estado[pasos[j][0]] for j in range(i)]
                        if not all(anteriores):
                            st.error(f"❌ No se puede marcar '{pasos[i][1]}' sin completar pasos anteriores.")
                            st.stop()

                try:
                    with st.spinner("🔄 Sincronizando con la nube..."):
                        now = datetime.now().isoformat(sep=" ", timespec="seconds")
                        ws = operacion_segura(lambda: sh.worksheet("actividades" if proc_name == "APROBACION" else "seguimiento"))
                        header = operacion_segura(lambda: ws.row_values(1))
                        row_idx = operacion_segura(lambda: ws.find(str(id_act if proc_name == "APROBACION" else comision))).row
                        for col, _ in pasos:
                            idx_col = header.index(col) + 1
                            ucol = f"{col}_user"
                            tcol = f"{col}_timestamp"
                            idx_u = header.index(ucol) + 1
                            idx_t = header.index(tcol) + 1
                            operacion_segura(lambda: ws.update_cell(row_idx, idx_col, estado[col]))
                            operacion_segura(lambda: ws.update_cell(row_idx, idx_u, st.session_state["name"]))
                            operacion_segura(lambda: ws.update_cell(row_idx, idx_t, now))
                        st.success("✅ Datos actualizados correctamente")
                        cargar_datos.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"Error al sincronizar: {str(e)}")
        else:
            st.info(f"🔒 No tenés permisos para editar {proc_name}.")

else:
    if st.session_state.get("authentication_status") is False:
        st.error("❌ Usuario o contraseña incorrectos.")
    else:
        st.warning("🔒 Ingresá tus credenciales para acceder.")
    st.stop()
