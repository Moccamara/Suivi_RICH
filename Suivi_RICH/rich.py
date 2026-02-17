import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw
import pandas as pd

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(layout="wide", page_title="RICH – Suivi")
st.title("🌍 RICH– Geospatial Monitoring Dashboard")

# =========================================================
# USERS AND REGIONS
# =========================================================
USERS = {
    "ro_rich": {"password": "rich2026rd", "role": "User", "regions": ["Kayes","Kita"]},
    "fo_rich": {"password": "rich2026ft", "role": "User", "regions": ["Bafoulabe","Kenieba"]},
    "bo_rich": {"password": "rich2026bk", "role": "User", "regions": ["Yelimane","Nioro","Diema"]},
    "admin": {"password": "admin2026", "role": "Admin", "cercles": []}
}

# =========================================================
# SESSION INIT
# =========================================================
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.accessible_regions = []
    st.session_state.points_gdf = None

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
        if username in USERS and password == USERS[username]["password"]:
            st.session_state.auth_ok = True
            st.session_state.username = username
            st.session_state.user_role = USERS[username]["role"]
            st.session_state.accessible_regions = USERS[username]["regions"]
            st.rerun()
        else:
            st.sidebar.error("❌ Invalid login or password")
    st.stop()

# =========================================================
# LOAD EMOP SE POLYGONS
# =========================================================
@st.cache_data(show_spinner=False)
def load_se_data():
    gdf = gpd.read_file("Suivi_RICH/data/SE_Test.geojson")
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)

    gdf.columns = [c.strip() for c in gdf.columns]  # keep exact names
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
    st.image("Suivi_RICH/logo/CVD_Mali.jpeg", width=200)
    st.markdown(f"**User:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

# =========================================================
# SAFE UNIQUE FUNCTION
# =========================================================
def unique_clean(series):
    if isinstance(series, pd.DataFrame): series = series.iloc[:,0]
    return sorted(series.dropna().astype(str).str.strip().unique())

# =========================================================
# ATTRIBUTE FILTERS
# =========================================================
st.sidebar.markdown("### 🗂️ Attribute Query")

# Region
all_regions = unique_clean(gdf["lregion"])
regions = all_regions if st.session_state.user_role=="Admin" else [r for r in all_regions if r in st.session_state.accessible_regions]
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
se_selected = st.sidebar.selectbox("SE (num_se)", se_list)
gdf_se = gdf_commune if se_selected=="No filter" else gdf_commune[gdf_commune["num_se"]==se_selected]

# =========================================================
# CSV UPLOAD AND FILTER BY CSV num_se BASED ON SELECTED COMMUNE
# =========================================================
st.sidebar.markdown("### 📥 Upload CSV Points")
csv_file = st.sidebar.file_uploader("Upload CSV", type=["csv"])
csv_points_filtered = None

if csv_file is not None:
    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.lower().str.strip()
    
    if {"latitude","longitude"}.issubset(df.columns):
        # Create GeoDataFrame
        gpts = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
            crs=4326
        )
        st.session_state.points_gdf = gpts

        # Keep only points inside the selected commune polygon(s)
        gdf_commune_proj = gdf_commune.to_crs(gpts.crs)
        points_in_commune = gpd.sjoin(
            gpts, gdf_commune_proj[["geometry"]], how="inner", predicate="within"
        )

        # CSV num_se selection based on points in commune
        if "num_se" in points_in_commune.columns:
            csv_se_list = ["No filter"] + sorted(points_in_commune["num_se"].dropna().astype(str).unique())
        else:
            csv_se_list = ["No filter"]

        csv_se_selected = st.sidebar.selectbox("CSV num_se", csv_se_list)

        # Filter points
        csv_points_filtered = (
            points_in_commune if csv_se_selected == "No filter"
            else points_in_commune[points_in_commune["num_se"].astype(str) == str(csv_se_selected)]
        )

        st.sidebar.success(f"✅ {len(points_in_commune)} points in selected commune")
    else:
        st.sidebar.error("CSV must contain latitude & longitude")

# =========================================================
# MAP
# =========================================================
if not gdf_se.empty:
    minx, miny, maxx, maxy = gdf_se.total_bounds
    m = folium.Map(location=[(miny+maxy)/2,(minx+maxx)/2], zoom_start=13, tiles=None)

    # Base maps
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite",
        overlay=False,
        control=True
    ).add_to(m)

    # SE polygons
    se_group = folium.FeatureGroup(name="SE Polygons")
    folium.GeoJson(
        gdf_se,
        tooltip=folium.GeoJsonTooltip(fields=["num_se","pop_se"], aliases=["SE","Population"]),
        style_function=lambda x: {"color":"blue","weight":2,"fillOpacity":0.2}
    ).add_to(se_group)
    se_group.add_to(m)

    # CSV points overlay
    if csv_points_filtered is not None and not csv_points_filtered.empty:
        csv_group = folium.FeatureGroup(name="CSV Points", show=True)
        for _, r in csv_points_filtered.iterrows():
            folium.CircleMarker(
                location=[r.geometry.y, r.geometry.x],
                radius=5,
                color="red",
                fill=True,
                fill_opacity=0.9,
                tooltip=f"Point Concession: SE {r.get('num_se','N/A')}"
            ).add_to(csv_group)
        csv_group.add_to(m)

    # Tools
    MeasureControl().add_to(m)
    Draw(export=True).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)

    m.fit_bounds([[miny,minx],[maxy,maxx]])
    st_folium(m, height=550, use_container_width=True)

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**RICH – Suivi Géospatial**  

**- Abdoul Karim DIAWARA**, Chef de Division Cartographie et SIG  
**- Dr. Mahamadou CAMARA, PhD – Geomatics Engineering**  
""")



















