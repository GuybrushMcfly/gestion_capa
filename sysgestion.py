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

with open("config.yaml") as file:
    config = yaml.load(file, Loader=SafeLoader)

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

        source_row = fila_act if proc_name == "APROBACION" else fila_seg
        temp_key = f"estado_{proc_name}_{id_act}_{comision}"
        if temp_key not in st.session_state:
            st.session_state[temp_key] = {}
            for col, _ in pasos:
                st.session_state[temp_key][col] = bool(source_row.get(col, False))

        # Visualización tipo stepper
        bools = [st.session_state[temp_key][col] for col, _ in pasos]
        idx = len(bools) if all(bools) else next((i for i, v in enumerate(bools) if not v), 0)
        fig = go.Figure()
        x, y = list(range(len(pasos))), 1
        color_completado = "#4DB6AC"
        color_actual = "#FF8A65"
        color_pendiente = "#D3D3D3"
        icono = {"finalizado": "✓", "actual": "⏳", "pendiente": "○"}

        for i in range(len(pasos)-1):
            clr = color_completado if i < idx else color_pendiente
            fig.add_trace(go.Scatter(x=[x[i], x[i+1]], y=[y, y], mode="lines",
                                     line=dict(color=clr, width=8), showlegend=False))

        for i, (col, label) in enumerate(pasos):
            estado = st.session_state[temp_key][col]
            if estado:
                clr, ic = color_completado, icono["finalizado"]
            elif i == idx:
                clr, ic = color_actual, icono["actual"]
            else:
                clr, ic = color_pendiente, icono["pendiente"]

            usuario = source_row.get(f"{col}_user", "").strip()
            timestamp = source_row.get(f"{col}_timestamp", "").strip()
            hover = label
            if usuario or timestamp:
                try:
                    # Convertir string UTC a datetime y ajustar -3 horas
                    ts_local = datetime.fromisoformat(timestamp) - pd.Timedelta(hours=3)
                    timestamp_fmt = ts_local.strftime("%d/%m/%Y %H:%M")
                    hover += f"<br>ULTIMA EDICIÓN:<br>{usuario} – {timestamp_fmt}"
                except:
                    hover += f"<br>ULTIMA EDICIÓN:<br>{usuario} – {timestamp}"
            else:
                hover += "<br>Sin información de edición"

            fig.add_trace(go.Scatter(x=[x[i]], y=[y], mode="markers+text",
                                     marker=dict(size=45, color=clr),
                                     text=[ic], textposition="middle center",
                                     textfont=dict(color="white", size=18),
                                     hovertext=[hover], hoverinfo="text", showlegend=False))
            fig.add_trace(go.Scatter(x=[x[i]], y=[y-0.15], mode="text",
                                     text=[label], textposition="bottom center",
                                     textfont=dict(color="white", size=12), showlegend=False))

        fig.update_layout(xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                          yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.3,1.2]),
                          height=180, margin=dict(l=20, r=20, t=30, b=0))
        st.plotly_chart(fig)

        if proc_name in perms["edit"]:
            with st.expander(f"🛠️ Editar {proc_name}"):
                for col, label in pasos:
                    st.session_state[temp_key][col] = st.checkbox(label, value=st.session_state[temp_key][col], key=f"{temp_key}_{col}")

        if proc_name in perms["edit"]:
            original_estado = {col: bool(source_row.get(col, False)) for col, _ in pasos}
            cambios_pendientes = any(st.session_state[temp_key][col] != original_estado[col] for col, _ in pasos)

            if cambios_pendientes:
                if st.button(f"💾 Actualizar {proc_name}"):
                    estado = st.session_state[temp_key]
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
