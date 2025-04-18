import streamlit as st
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials
import gspread
import json
import pandas as pd

# ——————————————
# 1) CARGA DE SHEETS
# ——————————————
scope = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(
    json.loads(st.secrets["GOOGLE_CREDS"]),
    scopes=scope
)
gc = gspread.authorize(creds)
sh = gc.open_by_key("1uYHnALX3TCaSzqJJFESOf8OpiaxKbLFYAQdcKFqbGrk")

df_actividades = pd.DataFrame(sh.worksheet("actividades").get_all_records())
df_comisiones  = pd.DataFrame(sh.worksheet("comisiones").get_all_records())
df_seguimiento = pd.DataFrame(sh.worksheet("seguimiento").get_all_records())

# Unimos para poder filtrar comisiones por curso
df_completo = (
    df_comisiones
    .merge(df_actividades[['Id_Actividad','NombreActividad']], on="Id_Actividad", how="left")
    .merge(df_seguimiento,           on="Id_Comision",     how="left")
)

# ——————————————
# 2) SELECCIÓN DE CURSO Y COMISIÓN
# ——————————————
curso = st.selectbox(
    "Seleccioná un Curso:",
    df_actividades["NombreActividad"].unique()
)
comisiones = df_completo.loc[
    df_completo["NombreActividad"] == curso, "Id_Comision"
].unique().tolist()

comision = st.selectbox("Seleccioná una Comisión:", comisiones)

# Traemos la fila de seguimiento correspondiente
fila = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]

# Obtenemos el worksheet para poder actualizar
ws_seguimiento = sh.worksheet("seguimiento")
header = ws_seguimiento.row_values(1)
row_idx = ws_seguimiento.find(str(comision)).row  # fila en Sheets

# ——————————————
# 3) CONFIGURACIÓN DE PROCESOS Y COLUMNAS
# ——————————————
procesos = {
    "APROBACION ACTIVIDAD": [
        ("A_Diseño","Diseño"),
        ("A_AutorizacionINAP","Autorización INAP"),
        ("A_CargaSAI","Carga SAI"),
        ("A_TramitacionExpediente","Tramitación Expediente"),
        ("A_DictamenINAP","Dictamen INAP"),
    ],
    "CAMPUS": [
        ("C_ArmadoAula","Armado Aula"),
        ("C_Matriculacion","Matriculación participantes"),
        ("C_AperturaCurso","Apertura Curso"),
        ("C_CierreCurso","Cierre Curso"),
        ("C_AsistenciaEvaluacion","Entrega Notas y Asistencia"),
    ],
    "DICTADO COMISION": [
        ("D_Difusion","Difusión"),
        ("D_AsignacionVacantes","Asignación Vacantes"),
        ("D_Cursada","Cursada"),
        ("D_AsistenciaEvaluacion","Asistencia y Evaluación"),
        ("D_CreditosSAI","Créditos SAI"),
        ("D_Liquidacion","Liquidación"),
    ]
}

# ——————————————
# PREPARAR WORKSHEET Y FILA ACTUAL
# ——————————————
ws_seguimiento = sh.worksheet("seguimiento")
header       = ws_seguimiento.row_values(1)
# localizar fila de la comisión actual
row_idx      = ws_seguimiento.find(str(comision)).row

# ——————————————
# 4) EDITOR DE CHECKBOXES (ACUMULA cambios)
# ——————————————
# Inicializar lista de cambios pendientes
if "cambios" not in st.session_state:
    st.session_state["cambios"] = []

st.markdown("## 🛠️ Editar estados por proceso\n*(los cambios se guardan al actualizar)*")
for proc, pasos in procesos.items():
    st.subheader(proc)
    for col_name, label in pasos:
        # Valor actual desde Sheets
        valor = bool(fila[col_name])
        # Checkbox editable solo si no está marcado
        nuevo = st.checkbox(
            label,
            value=valor,
            disabled=valor,
            key=f"{comision}_{col_name}"
        )
        # Acumular cambios en memoria
        if nuevo and not valor and col_name not in st.session_state["cambios"]:
            st.session_state["cambios"].append(col_name)

# Botón para enviar todos los cambios de golpe
if st.session_state["cambios"]:
    if st.button("💾 Actualizar cambios"):
        for col_name in st.session_state["cambios"]:
            col_idx = header.index(col_name) + 1
            try:
                ws_seguimiento.update_cell(row_idx, col_idx, True)
            except Exception as e:
                st.error(f"Error actualizando {col_name}: {e}")
        # Recargar datos y fila actualizada
        df_seguimiento = pd.DataFrame(ws_seguimiento.get_all_records())
        fila = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]
        row_idx = ws_seguimiento.find(str(comision)).row
        st.session_state["cambios"].clear()
        st.success("✅ Cambios actualizados correctamente.")

# ——————————————
# 5) STEPPER UI DINÁMICO (con datos frescos)
# ——————————————
st.markdown("---")
st.markdown("## 📊 Visualización del avance")

# (Re‐leer df_seguimiento para asegurarnos de tener los últimos valores)
df_seguimiento = pd.DataFrame(ws_seguimiento.get_all_records())
fila = df_seguimiento.loc[df_seguimiento["Id_Comision"] == comision].iloc[0]

color_completado = "#4DB6AC"
color_actual     = "#FF8A65"
color_pendiente  = "#D3D3D3"
icono = {"finalizado":"⚪","actual":"⏳","pendiente":"⚪"}

for proc, pasos in procesos.items():
    # Extraer booleans directamente desde la fila de pandas
    booleans = [ bool(fila[col_name]) for col_name,_ in pasos ]
    # Determinar índice del paso actual
    if all(booleans):
        estado_idx = len(pasos)
    else:
        estado_idx = next(i for i, v in enumerate(booleans) if not v)

    # Construcción del gráfico
    x   = list(range(len(pasos)))
    fig = go.Figure()
    y   = 1

    # Líneas
    for i in range(len(pasos)-1):
        clr = color_completado if i < estado_idx else color_pendiente
        fig.add_trace(go.Scatter(
            x=[x[i], x[i+1]],
            y=[y, y],
            mode="lines",
            line=dict(color=clr, width=8),
            showlegend=False
        ))

    # Puntos e íconos
    for i,(col_name,label) in enumerate(pasos):
        if i < estado_idx:
            clr,ic = color_completado, icono["finalizado"]
        elif i == estado_idx:
            clr,ic = color_actual,     icono["actual"]
        else:
            clr,ic = color_pendiente,  icono["pendiente"]

        fig.add_trace(go.Scatter(
            x=[x[i]], y=[y],
            mode="markers+text",
            marker=dict(size=45, color=clr),
            text=[ic],
            textposition="middle center",
            textfont=dict(color="white", size=18),
            showlegend=False
        ))
        fig.add_trace(go.Scatter(
            x=[x[i]], y=[y-0.15],
            mode="text",
            text=[label],
            textposition="bottom center",
            textfont=dict(color="white", size=12),
            showlegend=False
        ))

    fig.update_layout(
        title=dict(text=f"🔹 {proc}", x=0.01, xanchor="left", font=dict(size=16)),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.3,1.2]),
        height=180,
        margin=dict(l=20, r=20, t=30, b=0),
    )
    st.plotly_chart(fig)


