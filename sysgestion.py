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


# ────────────────────────────────────────────────
# 1) Definición de las secuencias de pasos
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

# ────────────────────────────────────────────────
# 2) Ahora sí definimos el diccionario de procesos
# ────────────────────────────────────────────────
PROCESOS = {
    "APROBACION": pasos_act,
    "CAMPUS":    pasos_campus,
    "DICTADO":   pasos_dictado,
}

# ────────────────────────────────────────────────
# 3) Y por fin los permisos sobre esos procesos
# ────────────────────────────────────────────────
PERMISOS = {
    "ADMIN":    {"view": set(PROCESOS),                    "edit": set(PROCESOS)},
    "CAMPUS":   {"view": set(PROCESOS),                    "edit": {"CAMPUS"}},
    "DISEÑO":   {"view": {"APROBACION"},                   "edit": {"APROBACION"}},
    "DICTADO":  {"view": set(PROCESOS),                    "edit": {"DICTADO"}},
    "INVITADO": {"view": set(PROCESOS),                    "edit": set()},
}

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

# Después de authenticator.login() y verificar que auth fue ok:
username = st.session_state["username"]
user_cfg = config["credentials"]["usernames"][username]
role     = user_cfg.get("role", "INVITADO")       # ADMIN, CAMPUS, DISEÑO, DICTADO, INVITADO
perms    = PERMISOS.get(role, PERMISOS["INVITADO"])


st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)


@st.cache_resource
def get_sheet(sheet_key: str):
    # 1) Autorización
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        json.loads(st.secrets["GOOGLE_CREDS"]),
        scopes=scope
    )
    gc = gspread.authorize(creds)
    # 2) Abrir la hoja UNA SOLA VEZ
    return gc.open_by_key(sheet_key)

# luego en el cuerpo:
sheet_key = "1uYHnALX3TCaSzqJJFESOf8OpiaxKbLFYAQdcKFqbGrk"
sh = get_sheet(sheet_key)


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
id_act   = df_actividades.loc[df_actividades["NombreActividad"] == curso, "Id_Actividad"].iloc[0]
fila_act = df_actividades.loc[df_actividades["Id_Actividad"] == id_act].iloc[0]
fila_seg = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]

# Prepare worksheets
ws_act      = sh.worksheet("actividades")
header_act  = ws_act.row_values(1)
row_idx_act = ws_act.find(str(id_act)).row

ws_seg      = sh.worksheet("seguimiento")
header_seg  = ws_seg.row_values(1)
row_idx_seg = ws_seg.find(str(comision)).row

# ────────────────────────────────────────────────
# PERMISOS SEGÚN ROL
# ────────────────────────────────────────────────
username = st.session_state["username"]
user_cfg = config["credentials"]["usernames"].get(username, {})
role     = user_cfg.get("role", "INVITADO")

PERMISOS = {
    "ADMIN":   {"view": {"APROBACION","CAMPUS","DICTADO"}, "edit": {"APROBACION","CAMPUS","DICTADO"}},
    "CAMPUS":  {"view": {"APROBACION","CAMPUS","DICTADO"}, "edit": {"CAMPUS"}},
    "DISEÑO":  {"view": {"APROBACION"},                  "edit": {"APROBACION"}},
    "DICTADO": {"view": {"APROBACION","CAMPUS","DICTADO"}, "edit": {"DICTADO"}},
    "INVITADO":{"view": {"APROBACION","CAMPUS","DICTADO"}, "edit": set()},
}
perms = PERMISOS.get(role, PERMISOS["INVITADO"])

# Colores e íconos
color_completado = "#4DB6AC"
color_actual     = "#FF8A65"
color_pendiente  = "#D3D3D3"
icono = {"finalizado":"⚪","actual":"⏳","pendiente":"⚪"}

# ────────────────────────────────────────────────
# PASOS DE APROBACIÓN
# ────────────────────────────────────────────────
pasos_act = [
    ("A_Diseño",                "Diseño"),
    ("A_AutorizacionINAP",      "Autorización INAP"),
    ("A_CargaSAI",              "Carga SAI"),
    ("A_TramitacionExpediente", "Tramitación Expediente"),
    ("A_DictamenINAP",          "Dictamen INAP"),
]

# 1) FORMULARIO EDITAR APROBACIÓN (solo si puede editar)
if "APROBACION" in perms["view"]:
    if "APROBACION" in perms["edit"]:
        with st.expander("🛠️ Editar APROBACIÓN ACTIVIDAD"):
            with st.form("form_aprob"):
                cambios = []
                for col, label in pasos_act:
                    marcado = bool(fila_act[col])
                    chk = st.checkbox(
                        label,
                        value=marcado,
                        disabled=marcado,
                        key=f"fa_{id_act}_{col}"
                    )
                    if chk and not marcado:
                        cambios.append(col)

                submitted = st.form_submit_button("💾 Actualizar APROBACIÓN")
                if submitted:
                    if not cambios:
                        st.warning("No seleccionaste ningún paso para actualizar.")
                    else:
                        errores = []
                        for col in cambios:
                            try:
                                # Booleano
                                idx_col = header_act.index(col) + 1
                                ws_act.update_cell(row_idx_act, idx_col, True)
                                # Usuario
                                ucol  = f"{col}_user"
                                idx_u = header_act.index(ucol) + 1
                                ws_act.update_cell(row_idx_act, idx_u, st.session_state["name"])
                                # Timestamp
                                tcol    = f"{col}_timestamp"
                                idx_t   = header_act.index(tcol) + 1
                                now_str = datetime.now().isoformat(sep=" ", timespec="seconds")
                                ws_act.update_cell(row_idx_act, idx_t, now_str)
                            except Exception as e:
                                errores.append((col, str(e)))

                        # recargar fila_act
                        df_act   = pd.DataFrame(ws_act.get_all_records())
                        fila_act = df_act.loc[df_act["Id_Actividad"] == id_act].iloc[0]

                        if errores:
                            for c, msg in errores:
                                st.error(f"Error actualizando {c}: {msg}")
                        else:
                            st.success("✅ Aprobación actualizada!")
    else:
        st.info("🔒 No tenés permisos para editar APROBACIÓN ACTIVIDAD.")

    # 2) STEPPER FIJO DE APROBACIÓN
    bools_act = [ bool(fila_act[col]) for col,_ in pasos_act ]
    idx_act   = len(bools_act) if all(bools_act) else next(i for i,v in enumerate(bools_act) if not v)

    fig_act = go.Figure()
    x = list(range(len(pasos_act))); y = 1

    # líneas
    for i in range(len(pasos_act)-1):
        clr = color_completado if i < idx_act else color_pendiente
        fig_act.add_trace(go.Scatter(
            x=[x[i], x[i+1]], y=[y, y],
            mode="lines",
            line=dict(color=clr, width=8),
            showlegend=False
        ))

    # puntos e íconos con hover
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

# ────────────────────────────────────────────────
# PASOS DE CAMPUS
# ────────────────────────────────────────────────
pasos_campus = [
    ("C_ArmadoAula",           "Armado Aula"),
    ("C_Matriculacion",        "Matriculación participantes"),
    ("C_AperturaCurso",        "Apertura Curso"),
    ("C_CierreCurso",          "Cierre Curso"),
    ("C_AsistenciaEvaluacion", "Entrega Notas y Asistencia"),
]

if "CAMPUS" in perms["view"]:
    if "CAMPUS" in perms["edit"]:
        with st.expander("🛠️ Editar CAMPUS"):
            with st.form("form_campus"):
                cambios = []
                for col, label in pasos_campus:
                    marcado = bool(fila_seg[col])
                    chk = st.checkbox(
                        label,
                        value=marcado,
                        disabled=marcado,
                        key=f"fc_{comision}_{col}"
                    )
                    if chk and not marcado:
                        cambios.append(col)

                submitted = st.form_submit_button("💾 Actualizar CAMPUS")
                if submitted:
                    if not cambios:
                        st.warning("No seleccionaste ningún paso para actualizar.")
                    else:
                        errores = []
                        for col in cambios:
                            try:
                                idx_col = header_seg.index(col) + 1
                                ws_seg.update_cell(row_idx_seg, idx_col, True)
                                ucol    = f"{col}_user"
                                idx_u   = header_seg.index(ucol) + 1
                                ws_seg.update_cell(row_idx_seg, idx_u, st.session_state["name"])
                                tcol    = f"{col}_timestamp"
                                idx_t   = header_seg.index(tcol) + 1
                                now     = datetime.now().isoformat(sep=" ", timespec="seconds")
                                ws_seg.update_cell(row_idx_seg, idx_t, now)
                            except Exception as e:
                                errores.append((col, str(e)))

                        # recarga
                        df_seg   = pd.DataFrame(ws_seg.get_all_records())
                        fila_seg = df_seg.loc[df_seg["Id_Comision"] == comision].iloc[0]

                        if errores:
                            for c, m in errores:
                                st.error(f"Error actualizando {c}: {m}")
                        else:
                            st.success("✅ Campus actualizado!")
    else:
        st.info("🔒 No tenés permisos para editar CAMPUS.")

    # STEPPER CAMPUS
    bools_campus = [ bool(fila_seg[col]) for col,_ in pasos_campus ]
    idx_campus  = len(bools_campus) if all(bools_campus) else next(i for i,v in enumerate(bools_campus) if not v)

    fig_campus = go.Figure()
    x = list(range(len(pasos_campus))); y = 1
    for i in range(len(pasos_campus)-1):
        clr = color_completado if i < idx_campus else color_pendiente
        fig_campus.add_trace(go.Scatter(
            x=[x[i], x[i+1]], y=[y, y],
            mode="lines",
            line=dict(color=clr, width=8),
            showlegend=False
        ))
    for i,(col,label) in enumerate(pasos_campus):
        if i < idx_campus:
            clr, ic = color_completado, icono["finalizado"]
        elif i == idx_campus:
            clr, ic = color_actual,     icono["actual"]
        else:
            clr, ic = color_pendiente,  icono["pendiente"]

        user = fila_seg.get(f"{col}_user","")
        ts   = fila_seg.get(f"{col}_timestamp","")
        hover = f"{label}<br>Por: {user}<br>El: {ts}"

        fig_campus.add_trace(go.Scatter(
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
        fig_campus.add_trace(go.Scatter(
            x=[x[i]], y=[y-0.15],
            mode="text",
            text=[label],
            textposition="bottom center",
            textfont=dict(color="white", size=12),
            showlegend=False
        ))
    fig_campus.update_layout(
        title=dict(text="🔹 CAMPUS", x=0.01, xanchor="left", font=dict(size=16)),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.3,1.2]),
        height=180, margin=dict(l=20, r=20, t=30, b=0),
    )
    st.plotly_chart(fig_campus)

# ────────────────────────────────────────────────
# PASOS DE DICTADO COMISIÓN
# ────────────────────────────────────────────────
pasos_dictado = [
    ("D_Difusion",               "Difusión"),
    ("D_AsignacionVacantes",     "Asignación Vacantes"),
    ("D_Cursada",                "Cursada"),
    ("D_AsistenciaEvaluacion",   "Asistencia y Evaluación"),
    ("D_CreditosSAI",            "Créditos SAI"),
    ("D_Liquidacion",            "Liquidación"),
]

if "DICTADO" in perms["view"]:
    if "DICTADO" in perms["edit"]:
        with st.expander("🛠️ Editar DICTADO COMISIÓN"):
            with st.form("form_dictado"):
                cambios = []
                for col, label in pasos_dictado:
                    marcado = bool(fila_seg[col])
                    chk = st.checkbox(
                        label,
                        value=marcado,
                        disabled=marcado,
                        key=f"fd_{comision}_{col}"
                    )
                    if chk and not marcado:
                        cambios.append(col)

                submitted = st.form_submit_button("💾 Actualizar DICTADO")
                if submitted:
                    if not cambios:
                        st.warning("No seleccionaste ningún paso para actualizar.")
                    else:
                        errores = []
                        for col in cambios:
                            try:
                                idx_col = header_seg.index(col) + 1
                                ws_seg.update_cell(row_idx_seg, idx_col, True)
                                ucol    = f"{col}_user"
                                idx_u   = header_seg.index(ucol) + 1
                                ws_seg.update_cell(row_idx_seg, idx_u, st.session_state["name"])
                                tcol    = f"{col}_timestamp"
                                idx_t   = header_seg.index(tcol) + 1
                                now     = datetime.now().isoformat(sep=" ", timespec="seconds")
                                ws_seg.update_cell(row_idx_seg, idx_t, now)
                            except Exception as e:
                                errores.append((col, str(e)))
                        # recarga
                        df_seg   = pd.DataFrame(ws_seg.get_all_records())
                        fila_seg = df_seg.loc[df_seg["Id_Comision"] == comision].iloc[0]
                        if errores:
                            for c, m in errores:
                                st.error(f"Error actualizando {c}: {m}")
                        else:
                            st.success("✅ Dictado actualizado!")
    else:
        st.info("🔒 No tenés permisos para editar DICTADO COMISIÓN.")

    # STEPPER DICTADO
    bools_dict = [ bool(fila_seg[col]) for col,_ in pasos_dictado ]
    idx_dict   = len(bools_dict) if all(bools_dict) else next(i for i,v in enumerate(bools_dict) if not v)

    fig_dict = go.Figure()
    x = list(range(len(pasos_dictado))); y = 1
    for i in range(len(pasos_dictado)-1):
        clr = color_completado if i < idx_dict else color_pendiente
        fig_dict.add_trace(go.Scatter(
            x=[x[i], x[i+1]], y=[y, y],
            mode="lines",
            line=dict(color=clr, width=8),
            showlegend=False
        ))
    for i,(col,label) in enumerate(pasos_dictado):
        if i < idx_dict:
            clr, ic = color_completado, icono["finalizado"]
        elif i == idx_dict:
            clr, ic = color_actual,     icono["actual"]
        else:
            clr, ic = color_pendiente,  icono["pendiente"]

        user = fila_seg.get(f"{col}_user","")
        ts   = fila_seg.get(f"{col}_timestamp","")
        hover = f"{label}<br>Por: {user}<br>El: {ts}"

        fig_dict.add_trace(go.Scatter(
            x=[x[i]], y=[y],
            mode="markers+text",
            marker=dict(size=45, color=clr),
            text=[ic], textposition="middle center",
            textfont=dict(color="white", size=18),
            hovertext=[hover], hoverinfo="text", showlegend=False
        ))
        fig_dict.add_trace(go.Scatter(
            x=[x[i]], y=[y-0.15], mode="text",
            text=[label], textposition="bottom center",
            textfont=dict(color="white", size=12), showlegend=False
        ))
    fig_dict.update_layout(
        title=dict(text="🔹 DICTADO COMISIÓN", x=0.01, xanchor="left", font=dict(size=16)),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.3,1.2]),
        height=180, margin=dict(l=20, r=20, t=30, b=0),
    )
    st.plotly_chart(fig_dict)

