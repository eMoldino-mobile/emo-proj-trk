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

# --- Firebase Initialization (with robust key handling from user) ---
def initialize_firebase():
    """Initializes Firebase Admin SDK using Streamlit secrets."""
    try:
        if not firebase_admin._apps:
            creds_raw = st.secrets["firebase_credentials"]

            # Step 1: Convert stringified dict to real dict if needed
            if isinstance(creds_raw, str):
                creds_dict = json.loads(creds_raw.replace("'", '"'))
            else:
                creds_dict = dict(creds_raw)  # ensure true dict type

            # Step 2: Fix escaped newlines if present
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
        # NOTE: This is a simplified login for this app's context.
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
    if not projects_df.empty:
        projects_df['firstContact'] = pd.to_datetime(projects_df.get('firstContact'), errors='coerce')
        projects_df['lastActivity'] = pd.to_datetime(projects_df.get('lastActivity'), errors='coerce').fillna(pd.Timestamp.min)
        projects_df = projects_df.sort_values(by='lastActivity', ascending=False)
    
    # Render UI
    st.dataframe(projects_df)

