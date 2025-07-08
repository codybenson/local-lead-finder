# app.py
import time
import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# show an error if the secret is missing
if "GCP_API_KEY" not in st.secrets:
    st.error("⚠️ Please add GCP_API_KEY under Settings → Secrets in Streamlit Cloud.")
    st.stop()
API_KEY = st.secrets["GCP_API_KEY"]

st.set_page_config(page_title="Local Lead Finder", layout="wide")
st.title("Local Lead Finder")

# ----- Inputs -----
address   = st.text_input("Center address", "Commerce, TX")
radius_mi = st.slider("Radius (miles)", 1, 30, 10)
keyword   = st.text_input("Keyword (blank = all)", "")

if st.button("Search"):
    # 1) Geocode
    geo = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": API_KEY}
    ).json()["results"][0]["geometry"]["location"]
    lat, lng = geo["lat"], geo["lng"]

    # 2) Nearby Search (with pagination)
    rows, token = [], ""
    while True:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params={
                "location": f"{lat},{lng}",
                "radius": int(radius_mi * 1609.34),
                "keyword": keyword,
                "key": API_KEY,
                "pagetoken": token
            }
        ).json()
        rows += resp.get("results", [])
        token = resp.get("next_page_token", "")
        if not token:
            break
        time.sleep(2)

    # 3) Fetch details & build DataFrame
    leads = []
    for p in rows:
        det = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": p["place_id"],
                "fields": "name,formatted_address,formatted_phone_number,website,geometry",
                "key": API_KEY
            }
        ).json().get("result", {})
        leads.append({
            "Name": det.get("name", ""),
            "Address": det.get("formatted_address", ""),
            "Phone": det.get("formatted_phone_number", ""),
            "Website": det.get("website", ""),
            "No Website?": not bool(det.get("website")),
            "Lat": det.get("geometry", {}).get("location", {}).get("lat"),
            "Lng": det.get("geometry", {}).get("location", {}).get("lng"),
        })

    df = pd.DataFrame(leads)
    st.success(f"Found {len(df)} businesses")
    st.download_button("⬇️ Download CSV", df.to_csv(index=False), "leads.csv", "text/csv")
    st.dataframe(df, use_container_width=True)

    # 4) Map
    fmap = folium.Map(location=[lat, lng], zoom_start=12)
    for row in leads:
        color = "red" if not row["Website"] else "green"
        folium.CircleMarker(
            [ row["Lat"], row["Lng"] ],
            radius=6, color=color, fill=True,
            tooltip=f"{row['Name']}\n{row['Website'] or '—'}"
        ).add_to(fmap)
    st_folium(fmap, height=550)
