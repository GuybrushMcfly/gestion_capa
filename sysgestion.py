import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import json
import pandas as pd

# ---- CONFIGURACIÓN DE PÁGINA ----
st.set_page_config(page_title="Gestión Capacitación DCYCP", layout="wide")

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

# Colores e íconos
color_completado = "#4DB6AC"
color_actual     = "#FF8A65"
color_pendiente  = "#D3D3D3"
icono = {"finalizado":"⚪","actual":"⏳","pendiente":"⚪"}

# ---- STEPPER FIJO DE LA ACTIVIDAD ----
pasos_act = [
    ("A_Diseño","Diseño"),
    ("A_AutorizacionINAP","Autorización INAP"),
    ("A_CargaSAI","Carga SAI"),
    ("A_TramitacionExpediente","Tramitación Expediente"),
    ("A_DictamenINAP","Dictamen INAP"),
]

bools_act = [bool(fila_act[col]) for col,_ in pasos_act]
idx_act = len(bools_act) if all(bools_act) else next(i for i,v in enumerate(bools_act) if not v)

fig_act = go.Figure()
x_act = list(range(len(pasos_act))); y=1
for i in range(len(pasos_act)-1):
    clr = color_completado if i<idx_act else color_pendiente
    fig_act.add_trace(go.Scatter(x=[x_act[i],x_act[i+1]], y=[y,y],
                                 mode="lines", line=dict(color=clr,width=8), showlegend=False))
for i,(col,label) in enumerate(pasos_act):
    clr,ic = (
        (color_completado, icono["finalizado"])
        if i<idx_act else
        (color_actual,     icono["actual"]) if i==idx_act else
        (color_pendiente,  icono["pendiente"])
    )
    user = fila_act.get(f"{col}_user","")
    ts   = fila_act.get(f"{col}_timestamp","")
    hover = f"{label}<br>Por: {user}<br>El: {ts}"
    fig_act.add_trace(go.Scatter(x=[x_act[i]], y=[y],
                                 mode="markers+text",
                                 marker=dict(size=45,color=clr),
                                 text=[ic], textposition="middle center",
                                 textfont=dict(color="white",size=18),
                                 hovertext=[hover], hoverinfo="text",
                                 showlegend=False))
    fig_act.add_trace(go.Scatter(x=[x_act[i]], y=[y-0.15],
                                 mode="text",
                                 text=[label],
                                 textposition="bottom center",
                                 textfont=dict(color="white",size=12),
                                 showlegend=False))
fig_act.update_layout(title=dict(text="🔹 APROBACIÓN ACTIVIDAD (Actividad)",x=0.01,xanchor="left",font=dict(size=16)),
                      xaxis=dict(showgrid=False,zeroline=False,showticklabels=False),
                      yaxis=dict(showgrid=False,zeroline=False,showticklabels=False,range=[0.3,1.2]),
                      height=180, margin=dict(l=20,r=20,t=30,b=0))
st.plotly_chart(fig_act)

# ---- FORM PARA EDITAR ESTADOS ----
procesos = {
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

with st.form("editor_form"):
    st.markdown("## 🛠️ Editar estados de Comisión")
    cambios = []
    for proc, pasos in procesos.items():
        st.subheader(proc)
        for col,label in pasos:
            val = bool(fila_seg[col])
            new = st.checkbox(label, value=val, disabled=val,
                              key=f"{comision}_{col}")
            if new and not val:
                cambios.append(col)
    submitted = st.form_submit_button("💾 Actualizar cambios")

if submitted and cambios:
    errs = []
    for col in cambios:
        ws, hdr, ridx = (ws_act,  header_act, row_idx_act) if col.startswith("A_") else (ws_seg, header_seg, row_idx_seg)
        try:
            # booleano
            cidx = hdr.index(col)+1
            ws.update_cell(ridx, cidx, True)
            # user
            ucol = f"{col}_user"; uidx = hdr.index(ucol)+1
            ws.update_cell(ridx, uidx, st.session_state["name"])
            # timestamp
            tcol = f"{col}_timestamp"; tidx = hdr.index(tcol)+1
            now = datetime.now().isoformat(sep=" ", timespec="seconds")
            ws.update_cell(ridx, tidx, now)
        except Exception as e:
            errs.append((col,str(e)))
    # recarga
    df_actividades = pd.DataFrame(ws_act.get_all_records())
    df_seguimiento = pd.DataFrame(ws_seg.get_all_records())
    fila_act = df_actividades.loc[df_actividades["Id_Actividad"]==id_act].iloc[0]
    fila_seg = df_seguimiento.loc[df_seguimiento["Id_Comision"]==comision].iloc[0]
    if errs:
        for c,m in errs: st.error(f"Error {c}: {m}")
    else:
        st.success("✅ Cambios guardados.")

# ---- STEPPER DINÁMICO DE COMISIÓN ----
st.markdown("---")
st.markdown("## 📊 Avance de Comisión")
for proc, pasos in procesos.items():
    bools = [bool(fila_seg[col]) for col,_ in pasos]
    idx = len(bools) if all(bools) else next(i for i,v in enumerate(bools) if not v)
    fig = go.Figure(); x=list(range(len(pasos))); y=1
    for i in range(len(pasos)-1):
        clr = color_completado if i<idx else color_pendiente
        fig.add_trace(go.Scatter(x=[x[i],x[i+1]], y=[y,y], mode="lines",
                                 line=dict(color=clr,width=8), showlegend=False))
    for i,(col,label) in enumerate(pasos):
        clr,ic = (
            (color_completado, icono["finalizado"])
            if i<idx else
            (color_actual,     icono["actual"]) if i==idx else
            (color_pendiente,  icono["pendiente"])
        )
        user = fila_seg.get(f"{col}_user","")
        ts   = fila_seg.get(f"{col}_timestamp","")
        hover = f"{label}<br>Por: {user}<br>El: {ts}"
        fig.add_trace(go.Scatter(x=[x[i]], y=[y], mode="markers+text",
                                 marker=dict(size=45,color=clr),
                                 text=[ic], textposition="middle center",
                                 textfont=dict(color="white",size=18),
                                 hovertext=[hover], hoverinfo="text", showlegend=False))
        fig.add_trace(go.Scatter(x=[x[i]], y=[y-0.15], mode="text",
                                 text=[label], textposition="bottom center",
                                 textfont=dict(color="white",size=12),
                                 showlegend=False))
    fig.update_layout(
        title=dict(text=f"🔹 {proc}", x=0.01, xanchor="left", font=dict(size=16)),
        xaxis=dict(showgrid=False,zeroline=False,showticklabels=False),
        yaxis=dict(showgrid=False,zeroline=False,showticklabels=False,range=[0.3,1.2]),
        height=180, margin=dict(l=20,r=20,t=30,b=0)
    )
    st.plotly_chart(fig)


