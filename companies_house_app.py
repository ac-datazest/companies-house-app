def clean_postcode(pc):
    return pc.upper().replace(" ", "").strip()

import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta
import hashlib

# --- AUTH ---
import hashlib

def check_login():
    def login_entered():
        user_hash = st.secrets["users"].get(st.session_state["username"])
        if user_hash and hashlib.sha256(st.session_state["password"].encode()).hexdigest() == user_hash:
            st.session_state["authenticated"] = True
            del st.session_state["password"]
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", key="password", on_change=login_entered)
        st.stop()
    elif not st.session_state["authenticated"]:
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", key="password", on_change=login_entered)
        st.error("❌ Incorrect username or password")
        st.stop()

check_login()

# --- CONFIG ---
API_KEY = "4bf2fdba-9628-412a-8640-55c914aed384"
BASE_URL = "https://api.company-information.service.gov.uk/advanced-search/companies"

# --- PAGE SETUP ---
st.set_page_config(page_title="Company Search Tool", layout="wide")
st.image("Logo - black & lime.png", width=200)
st.title("Companies House Search Tool")
st.markdown("Search UK companies by incorporation date, postcode, status, and SIC code. Download results as a CSV.")

# --- SIDEBAR FILTERS ---
with st.sidebar:
    st.header("Filters")

    use_recent = st.checkbox("Only show companies incorporated in the last X days")
    if use_recent:
        x_days = st.number_input("Number of days", min_value=1, max_value=365, value=30)
        incorp_to = date.today()
        incorp_from = incorp_to - timedelta(days=x_days)
        st.markdown(f"🔍 Searching from **{incorp_from}** to **{incorp_to}**")
    else:
        incorp_from = st.date_input("Incorporated from", value=date(2020, 1, 1))
        incorp_to = st.date_input("Incorporated to", value=date.today())

    status = st.selectbox("Company Status", ["", "active", "dissolved", "liquidation"])
    sic_input = st.text_input("SIC Codes (comma-separated, optional)", placeholder="e.g. 62012,82990")
    max_results = st.slider("Max Results", 10, 1000, 100, step=10)

    st.divider()
    st.markdown("### Postcode Filter")
    postcode = st.text_input("Single Postcode (optional)")
    uploaded_file = st.file_uploader("OR Upload CSV of Postcodes", type=["csv"])
    uploaded_postcodes = []

    if uploaded_file:
        try:
            df_upload = pd.read_csv(uploaded_file)
            possible_columns = [col for col in df_upload.columns if "post" in col.lower()]
            if possible_columns:
                selected_col = st.selectbox("Select postcode column", possible_columns)
                uploaded_postcodes = df_upload[selected_col].dropna().astype(str).str.upper().str.strip().unique().tolist()
                st.success(f"✅ Loaded {len(uploaded_postcodes)} postcodes.")
            else:
                st.warning("No column with name containing 'post' found.")
        except Exception as e:
            st.error(f"Error reading file: {e}")

# --- HELPER FUNCTIONS ---
def parse_sic_codes(raw_input):
    return [code.strip() for code in raw_input.split(",") if code.strip().isdigit()]

# --- API QUERY FUNCTION ---
def search_companies():
    collected = []
    postcode_list = uploaded_postcodes if uploaded_postcodes else [postcode] if postcode else [None]

    for pc in postcode_list:
        for start_index in range(0, max_results, 100):
            params = {
                "incorporated_from": incorp_from.strftime("%Y-%m-%d"),
                "incorporated_to": incorp_to.strftime("%Y-%m-%d"),
                "size": 100,
                "start_index": start_index
            }
            if pc:
                params["registered_office_address.postal_code"] = pc
            if status:
                params["company_status"] = status
            if sic_input:
                params["sic_codes"] = ",".join(parse_sic_codes(sic_input))

            response = requests.get(BASE_URL, params=params, auth=(API_KEY, ""))
            if response.status_code != 200:
                st.error(f"Error {response.status_code}: {response.text}")
                break

            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            collected.extend(items)

            if len(items) < 100:
                break

    # Apply manual postcode filtering
    if uploaded_postcodes:
        allowed = set(clean_postcode(pc) for pc in uploaded_postcodes)
        collected = [
            c for c in collected
            if clean_postcode(c.get("registered_office_address", {}).get("postal_code", "")) in allowed
        ]
    elif postcode:
        target = clean_postcode(postcode)
        collected = [
            c for c in collected
            if clean_postcode(c.get("registered_office_address", {}).get("postal_code", "")) == target
        ]

    return collected

# --- MAIN APP ---
if st.button("Search Companies"):
    with st.spinner("Fetching data..."):
        results = search_companies()
        if results:
            df = pd.DataFrame([{
                "Name": r.get("company_name"),
                "Number": r.get("company_number"),
                "Status": r.get("company_status"),
                "Type": r.get("company_type"),
                "Incorporated": r.get("date_of_creation"),
                "Ceased": r.get("date_of_cessation"),
                "Address": r.get("registered_office_address", {}).get("address_line_1", ""),
                "Locality": r.get("registered_office_address", {}).get("locality", ""),
                "Region": r.get("registered_office_address", {}).get("region", ""),
                "Postcode": r.get("registered_office_address", {}).get("postal_code", ""),
                "Country": r.get("registered_office_address", {}).get("country", ""),
                "SIC Codes": ", ".join(r.get("sic_codes", [])),
                "Insolvency History": r.get("has_insolvency_history", False),
                "Liquidated": r.get("has_been_liquidated", False)
            } for r in results])

            st.success(f"Returned {len(df)} companies.")
            st.dataframe(df)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download CSV", data=csv, file_name="companies.csv", mime="text/csv")
        else:
            st.warning("No results found.")
