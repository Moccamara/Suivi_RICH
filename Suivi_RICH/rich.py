import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw
import pandas as pd
import io
import os
import tempfile   # ✅ added for dynamic KML

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(layout="wide", page_title="REACH–Mali Suivi")
st.title("🌍 REACH–Mali Geospatial Data Monitoring Dashboard")

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
# SESSION INIT
# =========================================================
st.session_state.setdefault("auth_ok", False)
st.session_state.setdefault("username", None)
st.session_state.setdefault("user_role", None)
st.session_state.setdefault("accessible_lcercles", [])
st.session_state.setdefault("points_gdf", None)

# =========================================================
# LOGOUT FUNCTION
# =========================================================
def logout():
    st.session_state.clear()
    st.rerun()

# =========================================================
# LOGIN
# =========================================================
if not st.session_state.auth_ok:
    st.sidebar.header("🔐 Login")
    username = st.sidebar.text_input("Login")
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
            st.sidebar.error("❌ Invalid login or password")
    st.stop()

# =========================================================
# LOAD SE POLYGONS
# =========================================================
@st.cache_data(show_spinner=False)
def load_se_data():
    gdf = gpd.read_file("Suivi_RICH/data/SE_Test.geojson")
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)
    gdf.columns = [c.strip() for c in gdf.columns]
    for col in ["lregion","lcercle","lcommune","num_se","pop_se"]:
        if col not in gdf.columns:
            gdf[col] = None
    gdf = gdf[gdf.is_valid & ~gdf.is_empty]
    return gdf

try:
    gdf = load_se_data()
except Exception as e:
    st.error(f"❌ Unable to load RICH GeoJSON: {e}")
    st.stop()

# =========================================================
# SIDEBAR HEADER
# =========================================================
with st.sidebar:
    st.image("Suivi_RICH/logo/logos.jpg", width=300)
    st.markdown(f"**User:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

# =========================================================
# HELPER FUNCTION
# =========================================================
def unique_clean(series):
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:,0]
    return sorted(series.dropna().astype(str).str.strip().unique())

# =========================================================
# ATTRIBUTE FILTERS
# =========================================================
st.sidebar.markdown("### 🗂️ Attribute Query")

all_regions = unique_clean(gdf["lregion"])

if st.session_state.user_role == "Admin":
    regions = all_regions
else:
    user_cercles = st.session_state.accessible_lcercles
    allowed_regions = gdf[gdf["lcercle"].isin(user_cercles)]["lregion"].unique()
    regions = [r for r in all_regions if r in allowed_regions]

region = st.sidebar.selectbox("Region", regions)
gdf_r = gdf[gdf["lregion"] == region]

cercles = unique_clean(gdf_r["lcercle"])
if st.session_state.user_role != "Admin":
    cercles = [c for c in cercles if c in st.session_state.accessible_lcercles]

cercle = st.sidebar.selectbox("Cercle", cercles)
gdf_c = gdf_r[gdf_r["lcercle"] == cercle]

communes = unique_clean(gdf_c["lcommune"])
commune = st.sidebar.selectbox("Commune", communes)
gdf_commune = gdf_c[gdf_c["lcommune"] == commune]

se_list = ["No filter"] + unique_clean(gdf_commune["num_se"])
se_selected = st.sidebar.selectbox("SE (num_se)", se_list)

gdf_se = gdf_commune if se_selected=="No filter" else gdf_commune[gdf_commune["num_se"]==se_selected]

# =========================================================
# FOLIUM MAP
# =========================================================
if not gdf_se.empty:
    minx, miny, maxx, maxy = gdf_se.total_bounds
    m = folium.Map(location=[(miny+maxy)/2,(minx+maxx)/2], zoom_start=13, tiles=None)

    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite"
    ).add_to(m)

    se_group = folium.FeatureGroup(name="SE Polygons", show=True)
    folium.GeoJson(
        gdf_se,
        tooltip=folium.GeoJsonTooltip(fields=["num_se","pop_se"], aliases=["SE","Population"]),
        style_function=lambda f: {"color":"blue","weight":3,"fillColor":"cyan","fillOpacity":0.4}
    ).add_to(se_group)
    se_group.add_to(m)

    MeasureControl().add_to(m)
    Draw(export=True).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)

    m.fit_bounds([[miny,minx],[maxy,maxx]])
    st_folium(m, height=550, use_container_width=True)

# =========================================================
# SE NAVIGATION & KML DOWNLOAD (UPDATED ONLY HERE)
# =========================================================
if se_selected!="No filter" and not gdf_se.empty:

    st.markdown("### 🧭 Navigate & Download Selected SE")

    centroid = gdf_se.geometry.unary_union.centroid
    lat, lon = centroid.y, centroid.x
    google_maps_url = f"https://www.google.com/maps/@{lat},{lon},18z"

    st.markdown(
        f'<a href="{google_maps_url}" target="_blank">'
        f'<button style="background-color:#4CAF50;color:white;padding:10px 20px;'
        f'border:none;border-radius:5px;font-size:16px;">'
        f'🚗 Open SE in Google Maps (centroid)</button></a>',
        unsafe_allow_html=True
    )

    # ✅ DYNAMIC KML GENERATION (NO STATIC FILE NEEDED)
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".kml") as tmp:
            gdf_kml = gdf_se.to_crs(epsg=4326)
            gdf_kml.to_file(tmp.name, driver="KML")
            with open(tmp.name,"rb") as f:
                kml_bytes = f.read()

        st.download_button(
            label="📥 Download Selected SE Polygon (KML)",
            data=kml_bytes,
            file_name=f"SE_{se_selected}.kml",
            mime="application/vnd.google-earth.kml+xml"
        )

        st.info("Upload this file to Google My Maps to visualize the polygon.")

    except Exception as e:
        st.error(f"❌ Error generating KML: {e}")

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**REACH–MALI Geospatial Monitoring**

**- Abdoul Karim DIAWARA**, Chef de Division Cartographie et SIG  
**- Dr. Mahamadou CAMARA, PhD – Geomatics Engineering**
""")
