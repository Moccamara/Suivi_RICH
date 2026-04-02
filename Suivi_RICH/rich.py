import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw
import pandas as pd
import io
import os

# =========================================================
# PAGE CONFIG (ILIAD STYLE)
# =========================================================
st.set_page_config(
    layout="wide",
    page_title="REACH Mali WebGIS",
    page_icon="🌍"
)

# Hide Streamlit default UI
st.markdown("""
<style>

#MainMenu {visibility:hidden;}
footer {visibility:hidden;}
header {visibility:hidden;}

.block-container{
padding-top:1rem;
}

section[data-testid="stSidebar"]{
background-color:#f4f6fa;
}

</style>
""", unsafe_allow_html=True)

# =========================================================
# TITLE
# =========================================================
st.markdown("## 🌍 REACH–Mali Geospatial Monitoring WebGIS")

# =========================================================
# USERS
# =========================================================
USERS = {
    "ro_rich": {"password": "rich2026rd", "role": "User", "lcercles": ["Kayes", "Kita"]},
    "fo_rich": {"password": "rich2026ft", "role": "User", "lcercles": ["Bafoulabe", "Kenieba"]},
    "bo_rich": {"password": "rich2026bk", "role": "User", "lcercles": ["Yelimane", "Nioro", "Diema"]},
    "admin": {"password": "admin2026", "role": "Admin", "lcercles": []}
}

# =========================================================
# SESSION
# =========================================================
st.session_state.setdefault("auth_ok", False)
st.session_state.setdefault("username", None)
st.session_state.setdefault("user_role", None)
st.session_state.setdefault("accessible_lcercles", [])
st.session_state.setdefault("points_gdf", None)

# =========================================================
# LOGOUT
# =========================================================
def logout():
    st.session_state.clear()
    st.rerun()

# =========================================================
# LOGIN
# =========================================================
if not st.session_state.auth_ok:

    st.sidebar.image("Suivi_RICH/logo/logos.jpg", width=250)

    st.sidebar.header("🔐 REACH Login")

    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login"):

        user = USERS.get(username)

        if user and password == user["password"]:
            st.session_state.auth_ok = True
            st.session_state.username = username
            st.session_state.user_role = user["role"]
            st.session_state.accessible_lcercles = user["lcercles"]
            st.rerun()
        else:
            st.sidebar.error("Invalid credentials")

    st.stop()

# =========================================================
# SIDEBAR HEADER
# =========================================================
with st.sidebar:

    st.image("Suivi_RICH/logo/logos.jpg", width=250)

    st.markdown("## REACH Mali")
    st.markdown("Geospatial Monitoring")

    st.markdown("---")

    st.markdown("### 👤 User")

    st.write(st.session_state.username)
    st.write(st.session_state.user_role)

    if st.button("Logout"):
        logout()

# =========================================================
# LOAD DATA
# =========================================================
@st.cache_data
def load_data():

    gdf = gpd.read_file("Suivi_RICH/data/SE_Test.geojson")

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)

    return gdf

gdf = load_data()

# =========================================================
# FILTER FUNCTION
# =========================================================
def unique_clean(series):
    return sorted(series.dropna().astype(str).unique())

# =========================================================
# FILTERS
# =========================================================
st.sidebar.markdown("### 🗂️ Filters")

# Region
regions = unique_clean(gdf["lregion"])
region = st.sidebar.selectbox("Region", regions)

gdf_r = gdf[gdf["lregion"] == region]

# Cercle
cercles = unique_clean(gdf_r["lcercle"])
cercle = st.sidebar.selectbox("Cercle", cercles)

gdf_c = gdf_r[gdf_r["lcercle"] == cercle]

# Commune
communes = unique_clean(gdf_c["lcommune"])
commune = st.sidebar.selectbox("Commune", communes)

gdf_commune = gdf_c[gdf_c["lcommune"] == commune]

# SE
se_list = ["No filter"] + unique_clean(gdf_commune["num_se"])
se_selected = st.sidebar.selectbox("SE", se_list)

gdf_se = gdf_commune if se_selected=="No filter" else gdf_commune[gdf_commune["num_se"]==se_selected]

# =========================================================
# CSV UPLOAD
# =========================================================
st.sidebar.markdown("### 📥 Upload CSV")

csv_file = st.sidebar.file_uploader("Upload CSV", type="csv")

csv_points = None

if csv_file:

    df = pd.read_csv(csv_file)

    if {"latitude","longitude"}.issubset(df.columns):

        csv_points = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df.longitude, df.latitude),
            crs="EPSG:4326"
        )

# =========================================================
# MAP
# =========================================================
if not gdf_se.empty:

    bounds = gdf_se.total_bounds

    m = folium.Map(
        location=[(bounds[1]+bounds[3])/2,(bounds[0]+bounds[2])/2],
        zoom_start=12
    )

    # Base layers
    folium.TileLayer("OpenStreetMap").add_to(m)

    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        name="Google Satellite"
    ).add_to(m)

    # Polygon
    folium.GeoJson(
        gdf_se,
        tooltip=["num_se","pop_se"],
        style_function=lambda x:{
            "color":"blue",
            "weight":2
        }
    ).add_to(m)

    # CSV Points
    if csv_points is not None:

        for _,r in csv_points.iterrows():

            folium.CircleMarker(
                [r.geometry.y,r.geometry.x],
                radius=4,
                color="red"
            ).add_to(m)

    MeasureControl().add_to(m)
    Draw().add_to(m)

    folium.LayerControl().add_to(m)

    st_folium(
        m,
        height=750,
        use_container_width=True
    )

# =========================================================
# GOOGLE MAPS
# =========================================================
if se_selected!="No filter":

    centroid = gdf_se.geometry.unary_union.centroid

    lat = centroid.y
    lon = centroid.x

    url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

    st.markdown(
        f'<a href="{url}" target="_blank">'
        f'<button style="background-color:#4CAF50;color:white;padding:10px 20px;border:none;border-radius:5px;">'
        f'📍 Open in Google Maps</button></a>',
        unsafe_allow_html=True
    )

# =========================================================
# FOOTER
# =========================================================
st.markdown("---")

st.markdown("""
REACH Mali Monitoring System  

Dr. Mahamadou CAMARA  
Geomatics Engineer
""")
