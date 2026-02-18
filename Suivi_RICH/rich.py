import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw
import pandas as pd
import io  # <-- add this

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
    "admin": {"password": "admin2026", "role": "Admin", "lcercles": []}  # Admin sees all
}

# =========================================================
# SESSION INIT (safe initialization)
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
    st.image("Suivi_RICH/logo/logos.jpg", width=300)
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

# ---------------------------
# REGION
# ---------------------------
all_regions = unique_clean(gdf["lregion"])

if st.session_state.user_role == "Admin":
    regions = all_regions
else:
    # Keep only regions that contain user's cercles
    user_cercles = st.session_state.accessible_lcercles
    allowed_regions = gdf[gdf["lcercle"].isin(user_cercles)]["lregion"].unique()
    regions = [r for r in all_regions if r in allowed_regions]

region = st.sidebar.selectbox("Region", regions)
gdf_r = gdf[gdf["lregion"] == region]

# ---------------------------
# CERCLE
# ---------------------------
cercles = unique_clean(gdf_r["lcercle"])

if st.session_state.user_role != "Admin":
    cercles = [c for c in cercles if c in st.session_state.accessible_lcercles]

cercle = st.sidebar.selectbox("Cercle", cercles)
gdf_c = gdf_r[gdf_r["lcercle"] == cercle]

# ---------------------------
# COMMUNE
# ---------------------------
communes = unique_clean(gdf_c["lcommune"])
commune = st.sidebar.selectbox("Commune", communes)
gdf_commune = gdf_c[gdf_c["lcommune"] == commune]

# ---------------------------
# SE
# ---------------------------
se_list = ["No filter"] + unique_clean(gdf_commune["num_se"])
se_selected = st.sidebar.selectbox("SE (num_se)", se_list)

gdf_se = (
    gdf_commune
    if se_selected == "No filter"
    else gdf_commune[gdf_commune["num_se"] == se_selected]
)

# =========================================================
# CSV UPLOAD AND FILTER BY CSV num_se BASED ON SELECTED COMMUNE
# =========================================================
import io  # make sure at the top

# =========================================================
# CSV UPLOAD AND FILTER BY CSV num_se BASED ON SELECTED COMMUNE
# =========================================================
st.sidebar.markdown("### 📥 Upload CSV Points")
csv_file = st.sidebar.file_uploader("Upload CSV", type=["csv"])
csv_points_filtered = None

if csv_file is not None:

    # ---- READ FILE CONTENT FIRST ----
    content = csv_file.read().decode("utf-8", errors="ignore")
    first_line = content.splitlines()[0]

    # ---- MANUAL SEPARATOR DETECTION ----
    if "\t" in first_line:
        sep = "\t"
    elif ";" in first_line:
        sep = ";"
    else:
        sep = ","

    # ---- READ CSV SAFELY ----
    try:
        df = pd.read_csv(
            io.StringIO(content),
            sep=sep,
            engine="python",
            on_bad_lines="skip",
            encoding="utf-8",
            skip_blank_lines=True
        )
    except Exception as e:
        st.sidebar.error(f"❌ Failed to read CSV: {e}")
        df = None

    if df is not None and {"latitude", "longitude"}.issubset(df.columns):

        # ---- CLEAN COLUMN NAMES ----
        df.columns = df.columns.str.lower().str.strip()

        # Convert to numeric safely
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df = df.dropna(subset=["latitude", "longitude"])

        # Create GeoDataFrame
        gpts = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
            crs="EPSG:4326"
        )
        st.session_state.points_gdf = gpts

        # ---- SPATIAL FILTER INSIDE SELECTED COMMUNE ----
        gdf_commune_proj = gdf_commune.to_crs(gpts.crs)

        # Ensure num_se column exists
        if "num_se" not in gdf_commune_proj.columns:
            gdf_commune_proj["num_se"] = None

        # Spatial join: keep only points within the selected commune
        points_in_commune = gpd.sjoin(
            gpts,
            gdf_commune_proj[["geometry", "num_se"]],
            how="inner",
            predicate="within"
        )
        # ---- HANDLE POSSIBLE COLUMN RENAMING ----
        num_se_col = "num_se" if "num_se" in points_in_commune.columns else "num_se_right"
        # Convert to numeric safely
        points_in_commune["num_se"] = pd.to_numeric(
            points_in_commune[num_se_col],
            errors="coerce"
        ).astype("Int64")

        # Safe string column for filtering
        points_in_commune["num_se_str"] = points_in_commune["num_se"].astype(str)

        # ---- CSV num_se FILTER ACCORDING TO COMMUNE AND SORT NUMERICALLY ----
        valid_se = points_in_commune["num_se"].dropna().unique()
        valid_se_sorted = sorted(valid_se)  # numeric sort
        csv_se_list = ["No filter"] + [str(x) for x in valid_se_sorted]

        csv_se_selected = st.sidebar.selectbox("CSV num_se", csv_se_list)
        csv_points_filtered = (
            points_in_commune
            if csv_se_selected == "No filter"
            else points_in_commune[points_in_commune["num_se_str"] == csv_se_selected]
        )
        st.sidebar.success(f"✅ {len(csv_points_filtered)} points in selected commune")
    else:
        st.sidebar.error(
            f"CSV must contain latitude & longitude columns. Found: {df.columns.tolist()}"
        )
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
# NAVIGATE TO SELECTED SE (BEST PLACE HERE)
# =========================================================
# =========================================================
# NAVIGATION & KML DOWNLOAD FROM GITHUB
# =========================================================
if se_selected != "No filter" and not gdf_se.empty:
    st.markdown("### 🧭 Navigate & Download Selected SE")

    # 1️⃣ Google Maps Button (centroid)
    centroid = gdf_se.geometry.unary_union.centroid
    lat, lon = centroid.y, centroid.x
    google_maps_url = f"https://www.google.com/maps/@{lat},{lon},18z"
    
    st.markdown(
        f'<a href="{google_maps_url}" target="_blank">'
        f'<button style="background-color:#4CAF50;color:white;padding:10px 20px;border:none;border-radius:5px;font-size:16px;">'
        f'🚗 Open SE in Google Maps (centroid)</button></a>',
        unsafe_allow_html=True
    )

    # 2️⃣ Download KML from GitHub
    github_raw_url = f"https://raw.githubusercontent.com/username/repo_name/main/kml/SE_{se_selected}.kml"
    try:
        response = requests.get(github_raw_url)
        if response.status_code == 200:
            kml_bytes = response.content
            st.download_button(
                label="📥 Download SE Polygon (KML) for Google My Maps",
                data=kml_bytes,
                file_name=f"SE_{se_selected}.kml",
                mime="application/vnd.google-earth.kml+xml"
            )
        else:
            st.warning(f"KML file for SE {se_selected} not found on GitHub.")
    except Exception as e:
        st.error(f"❌ Error fetching KML from GitHub: {e}")

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**REACH–MALI Geostial Monitoring**  

**- Abdoul Karim DIAWARA**, Chef de Division Cartographie et SIG  
**- Dr. Mahamadou CAMARA, PhD – Geomatics Engineering**  
""")













































