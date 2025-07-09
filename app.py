# app.py
import math, time, requests, pandas as pd, streamlit as st

# — Secret check
if "GCP_API_KEY" not in st.secrets:
    st.error("⚠️ Please add GCP_API_KEY in Settings → Secrets")
    st.stop()
API_KEY = st.secrets["GCP_API_KEY"]

# — Page config
st.set_page_config(page_title="Local Lead Finder",
                   layout="wide",
                   initial_sidebar_state="collapsed")

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
address   = st.text_input("City", "Commerce, TX")
radius_mi = st.slider("Radius (miles)", 1, 50, 10)
keyword   = st.text_input("Keyword", "")
divisions = st.number_input(
    "Search Size",
    min_value=1, max_value=4, value=2,
    help="1: Max 60, 2: Max 120, 3: Max 180"
)

# — Choose display mode
view = st.radio("View mode", ["Table", "List (mobile-friendly)"], horizontal=True)

def make_grid_centers(lat, lng, radius_m, divisions):
    m_lat = 111_000
    m_lng = 111_000 * math.cos(math.radians(lat))
    step_lat = (radius_m*2)/divisions/m_lat
    step_lng = (radius_m*2)/divisions/m_lng
    offset = (divisions-1)/2
    return [
      (lat + (i-offset)*step_lat, lng + (j-offset)*step_lng)
      for i in range(divisions) for j in range(divisions)
    ]

def haversine(lat1, lon1, lat2, lon2):
    R=6371000
    φ1,φ2=math.radians(lat1),math.radians(lat2)
    dφ=math.radians(lat2-lat1)
    dλ=math.radians(lon2-lon1)
    a=math.sin(dφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(dλ/2)**2
    return R*2*math.atan2(math.sqrt(a), math.sqrt(1-a))

if st.button("Search"):
    # 1) Geocode center
    geo = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address":address, "key":API_KEY}
    ).json()["results"][0]["geometry"]["location"]
    lat,lng=geo["lat"],geo["lng"]
    radius_m=int(radius_mi*1609.34)

    # 2) Multi-circle Nearby Search
    centers = make_grid_centers(lat, lng, radius_m, divisions)
    raw=[]
    for lat_c,lng_c in centers:
        token=""
        while True:
            r = requests.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={
                  "location":f"{lat_c},{lng_c}",
                  "radius":radius_m,
                  "keyword":keyword,
                  "key":API_KEY,
                  "pagetoken":token
                }
            ).json()
            raw += r.get("results",[])
            token = r.get("next_page_token","")
            if not token: break
            time.sleep(2)

    # 3) Dedupe & filter back to the main circle
    unique = {p["place_id"]:p for p in raw}.values()
    rows = [
      p for p in unique
      if haversine(lat,lng,
                   p["geometry"]["location"]["lat"],
                   p["geometry"]["location"]["lng"]) <= radius_m
    ]

    # 4) Fetch details
    leads=[]
    for p in rows:
        det = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
              "place_id": p["place_id"],
              "fields": "name,formatted_address,formatted_phone_number,website",
              "key": API_KEY
            }
        ).json().get("result",{})
        leads.append({
            "Name": det.get("name",""),
            "Address": det.get("formatted_address",""),
            "Phone": det.get("formatted_phone_number",""),
            "Website": det.get("website",""),
            "No Website?": not bool(det.get("website"))
        })

    df = pd.DataFrame(leads)
    st.success(f"Found {len(df)} businesses")
    st.download_button("⬇️ Download CSV",
                       df.to_csv(index=False),
                       "leads.csv","text/csv")

    if view == "Table":
        st.dataframe(df, use_container_width=True)
    else:
        # List-style for mobile with website status in parentheses
        for lead in leads:
            has_site = bool(lead["Website"])
            label = f"{lead['Name']} ({'SEO Prospect' if has_site else 'Website Prospect'})"
            with st.expander(label):
                st.write("• Address:", lead["Address"])
                st.write("• Phone:", lead["Phone"])
                st.write("• Website:", lead["Website"] or "—")
