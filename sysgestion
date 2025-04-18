import json
import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import gspread
from google.oauth2.service_account import Credentials

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
    st.markdown(
        "<h1 style='font-size: 30px; color: white;'>Gestión Capacitación DCYCP</h1>",
        unsafe_allow_html=True
    )
elif st.session_state["authentication_status"] is False:
    st.error("❌ Usuario o contraseña incorrectos.")
    st.stop()
else:
    st.warning("🔒 Ingresá tus credenciales para acceder al dashboard.")
    st.stop()

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

# ---- CARGA DE DATOS DE GOOGLE SHEETS ----
scope = ["https://www.googleapis.com/auth/spreadsheets"]
credenciales_dict = json.loads(st.secrets["GOOGLE_CREDS"])
creds = Credentials.from_service_account_info(credenciales_dict, scopes=scope)
gc = gspread.authorize(creds)

sheet_key = "1uYHnALX3TCaSzqJJFESOf8OpiaxKbLFYAQdcKFqbGrk"
sh = gc.open_by_key(sheet_key)

# Cargar cada hoja en un DataFrame
df_actividades = pd.DataFrame(sh.worksheet("actividades").get_all_records())
df_comisiones  = pd.DataFrame(sh.worksheet("comisiones").get_all_records())
df_seguimiento = pd.DataFrame(sh.worksheet("seguimiento").get_all_records())
df_resumen     = pd.DataFrame(sh.worksheet("resumen").get_all_records())

# Unir actividades + comisiones + seguimiento
df_completo = (
    df_comisiones
    .merge(df_actividades[['Id_Actividad', 'NombreActividad']],
           on="Id_Actividad", how="left")
    .merge(df_seguimiento, on="Id_Comision", how="left")
)

# ---- VISUALIZAR DATAFRAMES EN PESTAÑAS ----
tabs = st.tabs([
    "📋 Actividades",
    "📋 Comisiones",
    "📋 Seguimiento",
    "📋 Resumen",
    "🔗 Combinado"
])

with tabs[0]:
    st.subheader("Actividades")
    st.dataframe(df_actividades)

with tabs[1]:
    st.subheader("Comisiones")
    st.dataframe(df_comisiones)

with tabs[2]:
    st.subheader("Seguimiento")
    st.dataframe(df_seguimiento)

with tabs[3]:
    st.subheader("Resumen")
    st.dataframe(df_resumen)

with tabs[4]:
    st.subheader("Datos Combinados (Actividades + Comisiones + Seguimiento)")
    st.dataframe(df_completo)

# ---- EJEMPLO DE FILTROS (opcional) ----
# Si quisieras filtrar por un campo de df_resumen, por ejemplo 'EstadoComision':
# estados = df_resumen["EstadoComision"].dropna().unique().tolist()
# seleccionados = st.sidebar.multiselect(
#     "Filtrar por EstadoComision:",
#     options=sorted(estados),
#     default=sorted(estados)
# )
# df_filtrado = df_resumen[df_resumen["EstadoComision"].isin(seleccionados)]
# with tabs[3]:
#     st.subheader("Resumen (FILTRADO)")
#     st.dataframe(df_filtrado)

# El resto de tu lógica (checkboxes, gráficos, etc.) la añades debajo en nuevas pestañas o bloques.
