# app.py
import time
import requests
import pandas as pd
import streamlit as st

# — check for secret
if "GCP_API_KEY" not in st.secrets:
    st.error("⚠️ Please add GCP_API_KEY in Settings → Secrets")
    st.stop()
API_KEY = st.secrets["GCP_API_KEY"]

st.set_page_config(
    page_title="Local Lead Finder",
    layout="wide",
    initial_sidebar_state="collapsed"
)
st.title("Local Lead Finder")

# — Inputs
address   = st.text_input("Center address", "Commerce, TX")
radius_mi = st.slider("Radius (miles)", 1, 30, 10)
keyword   = st.text_input("Keyword (blank = all)", "")

if st.button("Search"):
    # 1) Geocode the center
    geo = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": API_KEY}
    ).json()["results"][0]["geometry"]["location"]
    lat, lng = geo["lat"], geo["lng"]

    # 2) Nearby search (with pagination)
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

    # 3) Pull details
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

    # 4) Show results
    df = pd.DataFrame(leads)
    st.success(f"Found {len(df)} businesses")
    st.download_button("⬇️ Download CSV", df.to_csv(index=False),
                       "leads.csv", "text/csv")
    st.dataframe(df, use_container_width=True)
