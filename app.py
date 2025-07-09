# app.py
import math
import time
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urlparse

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

# — Inject mobile-friendly CSS
st.markdown(
    """
    <style>
      /* Make the dataframe container scrollable horizontally */
      .stDataFrame > div { overflow-x: auto; }
      /* Tighten up padding so it fits more on a small screen */
      .streamlit-table td, .streamlit-table th { padding: 4px 8px; }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("Local Lead Finder")

# — Inputs
address   = st.text_input("City or address", "Commerce, TX")
radius_mi = st.slider("Radius (miles)", 1, 50, 10)
keyword   = st.text_input("Keyword (blank=all)", "")
divisions = st.number_input(
    "Search Size (multiples of 60 results)",
    min_value=1, max_value=4, value=2,
    help="1→60, 2→120, 3→180 max results"
)

# — Load exclusions (names or domains) from file
excluded = []
try:
    with open('exclusions.txt') as f:
        for line in f:
            val = line.strip().lower()
            if val:
                excluded.append(val)
except FileNotFoundError:
    st.warning("No exclusions file found (exclusions.txt) — proceeding without exclusions.")

# — Choose display mode
display_mode = st.radio(
    "View mode", ["Table", "List (mobile-friendly)"], horizontal=True
)

# Helpers
def make_grid_centers(lat, lng, radius_m, divisions):
    m_lat = 111_000
    m_lng = 111_000 * math.cos(math.radians(lat))
    step_lat = (radius_m * 2) / divisions / m_lat
    step_lng = (radius_m * 2) / divisions / m_lng
    offset = (divisions - 1) / 2
    return [
        (lat + (i - offset) * step_lat, lng + (j - offset) * step_lng)
        for i in range(divisions) for j in range(divisions)
    ]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2)**2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2)**2
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
    centers = make_grid_centers(lat, lng, radius_m, divisions)
    raw_results = []
    for lat_c, lng_c in centers:
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
            raw_results += resp.get("results", [])
            token = resp.get("next_page_token", "")
            if not token:
                break
            time.sleep(2)

    # 3) De-dupe & filter back to circle
    unique = {p["place_id"]: p for p in raw_results}.values()
    filtered = [
        p for p in unique
        if haversine(
            lat, lng,
            p["geometry"]["location"]["lat"],
            p["geometry"]["location"]["lng"]
        ) <= radius_m
    ]

    # 4) Fetch details & apply exclusions
    leads = []
    for p in filtered:
        det = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": p["place_id"],
                "fields": "name,formatted_address,formatted_phone_number,website",
                "key": API_KEY
            }
        ).json().get("result", {})
        name = det.get("name", "").strip()
        website = det.get("website", "")
        domain = urlparse(website).netloc.lower() if website else ""
        # skip if any exclusion matches name or domain
        if any(ex in name.lower() or ex in domain for ex in excluded):
            continue
        leads.append({
            "Name": name,
            "Address": det.get("formatted_address", ""),
            "Phone": det.get("formatted_phone_number", ""),
            "Website": website,
            "Type": "SEO Prospect" if website else "Website Prospect"
        })

    # 5) Display results
    df = pd.DataFrame(leads)
    st.success(f"Found {len(df)} businesses after exclusions")
    st.download_button(
        "⬇️ Download CSV",
        df.to_csv(index=False),
        "leads.csv", "text/csv"
    )

    if display_mode == "Table":
        st.dataframe(df, use_container_width=True)
    else:
        for lead in leads:
            label = f"{lead['Name']} ({lead['Type']})"
            with st.expander(label):
                st.write("• Address:", lead["Address"])
                st.write("• Phone:", lead["Phone"])
                st.write("• Website:", lead["Website"] or "—")
