import streamlit as st

st.write("🔑 Secrets available:", st.secrets.keys())

# app.py
import os
import time
import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

API_KEY = st.secrets["GCP_API_KEY"]  # loaded from Streamlit secrets

st.set_page_config(page_title="Local Lead Finder", layout="wide")
st.title("Local Lead Finder")

# ----- Inputs -----
address   = st.text_input("Center address", "Commerce, TX")
radius_mi = st.slider("Radius (miles)", 1, 50, 10)
keyword   = st.text_input("Keyword (blank = all)", "")

if st.button("Search"):
    # Geocode
    geo = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": API_KEY}
    ).json()["results"][0]["geometry"]["location"]
    lat, lng = geo["lat"], geo["lng"]

    # Nearby Search (with pagination)
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
        rows += resp["results"]
        token = resp.get("next_page_token","")
        if not token: break
        time.sleep(2)

    # Fetch details
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
            "Name": det.get("name",""),
            "Address": det.get("formatted_address",""),
            "Phone": det.get("formatted_phone_number",""),
            "Website": det.get("website",""),
            "No Website?": "✅" if not det.get("website") else ""
        })

    df = pd.DataFrame(leads)
    st.success(f"Found {len(df)} businesses")
    st.download_button("⬇️ Download CSV", df.to_csv(index=False), "leads.csv","text/csv")
    st.dataframe(df, use_container_width=True)

    # Map
    fmap = folium.Map(location=[lat,lng], zoom_start=12)
    for idx, row in df.iterrows():
        # Lookup lat/lng back in the original rows list
        geopt = next((x["geometry"]["location"] 
                      for x in rows if x["place_id"] == rows[idx]["place_id"]), None)
        if geopt:
            folium.CircleMarker(
                [geopt["lat"], geopt["lng"]],
                radius=6,
                color="red" if row["No Website?"] else "green",
                fill=True,
                tooltip=row["Name"]
            ).add_to(fmap)
    st_folium(fmap, height=550)
