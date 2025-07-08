# app.py
import math
import time
import requests
import pandas as pd
import streamlit as st

# — Secret check
if "GCP_API_KEY" not in st.secrets:
    st.error("⚠️ Please add GCP_API_KEY in Settings → Secrets")
    st.stop()
API_KEY = st.secrets["GCP_API_KEY"]

# — Page config
st.set_page_config(
    page_title="Local Lead Finder",
    layout="wide",
    initial_sidebar_state="collapsed"
)
st.title("Local Lead Finder")

# — Inputs
address   = st.text_input("Center address", "Commerce, TX")
radius_mi = st.slider("Radius (miles)", 1, 50, 10)
keyword   = st.text_input("Keyword (blank = all)", "")
divisions = st.number_input(
    "Grid divisions per axis",
    min_value=1, max_value=4, value=2,
    help="1→1 search (60 max), 2→4 searches, 3→9 searches, etc."
)

def make_grid_centers(lat, lng, radius_m, divisions):
    """Return a grid of (lat, lng) centers covering the circle."""
    m_per_deg_lat = 111_000
    m_per_deg_lng = 111_000 * math.cos(math.radians(lat))
    step_lat = (radius_m * 2) / divisions / m_per_deg_lat
    step_lng = (radius_m * 2) / divisions / m_per_deg_lng

    centers = []
    offset = (divisions - 1) / 2
    for i in range(divisions):
        for j in range(divisions):
            lat_i = lat + (i - offset) * step_lat
            lng_j = lng + (j - offset) * step_lng
            centers.append((lat_i, lng_j))
    return centers

def haversine(lat1, lon1, lat2, lon2):
    """Return distance in meters between two lat/lng points."""
    R = 6371000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

if st.button("Search"):
    # 1) Geocode center
    geo = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": API_KEY}
    ).json()["results"][0]["geometry"]["location"]
    lat, lng = geo["lat"], geo["lng"]
    radius_m = int(radius_mi * 1609.34)

    # 2) Multi-center Nearby Search
    grid_centers = make_grid_centers(lat, lng, radius_m, divisions)
    all_places = []
    for (lat_c, lng_c) in grid_centers:
        token = ""
        while True:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={
                    "location": f"{lat_c},{lng_c}",
                    "radius": radius_m,
                    "keyword": keyword,
                    "key": API_KEY,
                    "pagetoken": token
                }
            ).json()
            all_places += resp.get("results", [])
            token = resp.get("next_page_token", "")
            if not token:
                break
            time.sleep(2)

    # 3) De-dupe & filter back to circle
    unique = {p["place_id"]: p for p in all_places}.values()
    rows = [
        p for p in unique
        if haversine(lat, lng,
                     p["geometry"]["location"]["lat"],
                     p["geometry"]["location"]["lng"])
           <= radius_m
    ]

    # 4) Fetch details
    leads = []
    for p in rows:
        det = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": p["place_id"],
                "fields": "name,formatted_address,formatted_phone_number,website",
                "key": API_KEY
            }
        ).json().get("result", {})
        leads.append({
            "Name": det.get("name", ""),
            "Address": det.get("formatted_address", ""),
            "Phone": det.get("formatted_phone_number", ""),
            "Website": det.get("website", ""),
            "No Website?": "✅" if not det.get("website") else ""
        })

    # 5) Display results
    df = pd.DataFrame(leads)
    st.success(f"Found {len(df)} businesses")
    st.download_button(
        "⬇️ Download CSV",
        df.to_csv(index=False),
        "leads.csv", "text/csv"
    )
    st.dataframe(df, use_container_width=True)
