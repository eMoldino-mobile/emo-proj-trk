import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth
import pandas as pd
import altair as alt
from datetime import datetime
import json

# --- Page Configuration ---
st.set_page_config(
    page_title="Project Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Firebase Initialization (with robust key handling) ---
def initialize_firebase():
    """Initializes Firebase Admin SDK using Streamlit secrets."""
    try:
        if not firebase_admin._apps:
            creds_raw = st.secrets["firebase_credentials"]

            # Step 1: Ensure it's a dictionary
            if isinstance(creds_raw, str):
                creds_dict = json.loads(creds_raw.replace("'", '"'))
            else:
                creds_dict = dict(creds_raw)

            # Step 2: Fix escaped newlines in the private key
            if "private_key" in creds_dict and "\\n" in creds_dict["private_key"]:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            # Step 3: Initialize Firebase
            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)

        return firestore.client()

    except Exception as e:
        st.error(f"Firebase initialization failed. Please ensure your secrets.toml is configured correctly.\n\nError: {e}")
        st.stop()

db = initialize_firebase()

# --- User Authentication ---
def login_user(email, password):
    """Authenticates a user."""
    try:
        # NOTE: This is a simplified login. For production, use Firebase Client SDKs or custom tokens.
        user = firebase_auth.get_user_by_email(email)
        st.session_state.logged_in = True
        st.session_state.user_email = user.email
        st.session_state.role = st.secrets["user_roles"].get(user.email, "readonly")
        st.rerun()
    except Exception as e:
        st.error(f"Login Failed: {e}")

def logout_user():
    """Logs out the current user."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- Data Fetching ---
@st.cache_data(ttl=60)
def fetch_collection(_collection_name):
    """Fetches a collection and caches it."""
    docs = db.collection(_collection_name).stream()
    return [doc.to_dict() | {'id': doc.id} for doc in docs]

# --- Main App ---
if not st.session_state.get('logged_in'):
    st.title("eMOLDINO")
    st.header("Project Dashboard Login")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            login_user(email, password)
else:
    # --- Main Dashboard UI ---
    st.sidebar.title("Dashboard Menu")
    st.sidebar.write("Logged in as:")
    st.sidebar.info(st.session_state.user_email)
    st.sidebar.button("Logout", on_click=logout_user, use_container_width=True)

    st.title("eMOLDINO Project Dashboard")

    projects_df = pd.DataFrame(fetch_collection("projects"))
    
    # Robustly handle data types and sorting
    if not projects_df.empty:
        if 'firstContact' in projects_df.columns:
            projects_df['firstContact'] = pd.to_datetime(projects_df['firstContact'], errors='coerce')
        
        # Ensure lastActivity column exists before trying to sort by it
        if 'lastActivity' in projects_df.columns:
            projects_df['lastActivity'] = pd.to_datetime(projects_df['lastActivity'], errors='coerce')
            # Fill any null/NaT values with a very old date to ensure they sort last
            projects_df['lastActivity'] = projects_df['lastActivity'].fillna(pd.Timestamp.min)
            projects_df = projects_df.sort_values(by='lastActivity', ascending=False)
        else:
            # If the column doesn't exist at all, add it with default values
            projects_df['lastActivity'] = pd.Timestamp.min
    
    settings_data = {
        'regions': sorted([item.get('name', '') for item in fetch_collection("regions")]),
        'pocs': sorted([item.get('name', '') for item in fetch_collection("pocs")]),
    }

    summary_tab, npi_tab, retrofit_tab = st.tabs(["Executive Summary", "NPI Projects", "Retrofit Projects"])

    with summary_tab:
        st.header("Executive Summary")
        business_area_filter = st.radio("Business Area", ["All", "External", "Internal"], horizontal=True, key="summary_area")
        
        summary_data = projects_df.copy()
        if business_area_filter != "All":
            summary_data = summary_data[summary_data['businessArea'] == business_area_filter]

        if not summary_data.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Total Sensors by Region")
                sensors_data = summary_data.groupby('region')['quantities'].apply(
                    lambda x: sum(item.get('sensor', {}).get('qty', 0) for item in x if isinstance(item, dict))
                ).reset_index(name='total_sensors')
                chart = alt.Chart(sensors_data).mark_bar().encode(x='region:N', y='total_sensors:Q').interactive()
                st.altair_chart(chart, use_container_width=True)

            with c2:
                st.subheader("Project Status Overview")
                status_counts = summary_data['status'].value_counts().reset_index(name='count')
                chart = alt.Chart(status_counts).mark_arc(innerRadius=50).encode(
                    theta='count:Q', color=alt.Color('status:N', title="Status")
                ).interactive()
                st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No data for summary.")

    def render_project_page(project_type, data):
        st.subheader(f"Filters for {project_type} Projects")
        f_cols = st.columns(4)
        area_f = f_cols[0].radio("Area", ["All", "External", "Internal"], key=f"{project_type}_area", horizontal=True)
        region_f = f_cols[1].selectbox("Region", ["All"] + settings_data["regions"], key=f"{project_type}_region")
        poc_f = f_cols[2].selectbox("POC", ["All"] + settings_data["pocs"], key=f"{project_type}_poc")
        
        filtered_data = data.copy()
        if area_f != 'All':
            filtered_data = filtered_data[filtered_data['businessArea'] == area_f]
        if region_f != 'All':
            filtered_data = filtered_data[filtered_data['region'] == region_f]
        if poc_f != 'All':
            filtered_data = filtered_data[filtered_data['mainPoc'] == poc_f]
            
        st.dataframe(filtered_data.drop(columns=['id', 'quantities', 'lastActivity'], errors='ignore'), use_container_width=True)

    with npi_tab:
        render_project_page("NPI", projects_df[projects_df['isNPI'] == "Yes"] if not projects_df.empty and 'isNPI' in projects_df.columns else pd.DataFrame())

    with retrofit_tab:
        render_project_page("Retrofit", projects_df[projects_df['isNPI'] == "No"] if not projects_df.empty and 'isNPI' in projects_df.columns else pd.DataFrame())

