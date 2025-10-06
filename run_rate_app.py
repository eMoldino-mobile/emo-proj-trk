import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth
import pandas as pd
import altair as alt
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="Project Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Firebase Initialization (with robust key handling) ---
def initialize_firebase():
    """Initializes Firebase Admin SDK using Streamlit secrets."""
    if not firebase_admin._apps:
        try:
            creds_dict = st.secrets["firebase_credentials"]

            # Fix for escaped newlines in the private key
            if "private_key" in creds_dict and "\\n" in creds_dict["private_key"]:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Firebase initialization failed. Please ensure your secrets.toml is configured correctly. Error: {e}")
            st.stop()
    return firestore.client()

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

# --- Data Fetching & Caching ---
@st.cache_data(ttl=60)
def fetch_collection(_collection_name):
    """Fetches a collection and caches it."""
    docs = db.collection(_collection_name).stream()
    return [doc.to_dict() | {'id': doc.id} for doc in docs]

@st.cache_data(ttl=60)
def fetch_comments(_project_id):
    """Fetches comments for a single project."""
    comments_ref = db.collection("projects").document(_project_id).collection("comments").order_by("timestamp").stream()
    return [comment.to_dict() | {'id': comment.id} for comment in comments_ref]

# --- Main App ---
if not st.session_state.get('logged_in'):
    # --- Login Page ---
    st.title("eMOLDINO")
    st.header("Project Dashboard Login")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            login_user(email, password)
else:
    # --- Main Dashboard ---
    st.sidebar.title("Dashboard Menu")
    st.sidebar.write(f"Logged in as:")
    st.sidebar.info(st.session_state.user_email)
    st.sidebar.button("Logout", on_click=logout_user, use_container_width=True)
    if st.session_state.role == 'editor':
        if st.sidebar.button("Add New Project", use_container_width=True, type="primary"):
            # This part will be handled by a modal in a more advanced setup
            st.warning("Add/Edit functionality would be in a modal here.")

    st.title("eMOLDINO Project Dashboard")

    # Fetch data
    projects_df = pd.DataFrame(fetch_collection("projects"))
    if not projects_df.empty:
        projects_df['firstContact'] = pd.to_datetime(projects_df['firstContact'], errors='coerce')
        projects_df['lastActivity'] = pd.to_datetime(projects_df.get('lastActivity'), errors='coerce').fillna(pd.Timestamp.min)
        projects_df = projects_df.sort_values(by='lastActivity', ascending=False)
        
    settings_data = {
        'regions': sorted([item.get('name', '') for item in fetch_collection("regions")]),
        'pocs': sorted([item.get('name', '') for item in fetch_collection("pocs")]),
    }

    summary_tab, npi_tab, retrofit_tab = st.tabs(["Executive Summary", "NPI Projects", "Retrofit Projects"])

    with summary_tab:
        # --- Summary Filters ---
        col1, col2 = st.columns([1,3])
        business_area_filter = col1.radio("Business Area", ["All", "External", "Internal"], horizontal=True, key="summary_area")
        
        summary_data = projects_df.copy()
        if business_area_filter != "All":
            summary_data = summary_data[summary_data['businessArea'] == business_area_filter]

        # --- Summary Charts ---
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
                status_counts = summary_data['status'].value_counts().reset_index()
                chart = alt.Chart(status_counts).mark_arc(innerRadius=50).encode(
                    theta='count:Q', color='status:N'
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
        
        st.subheader("Project Details")
        for _, row in filtered_data.iterrows():
            with st.expander(f"{row.get('supplierName', 'N/A')} - {row.get('status', 'N/A')}"):
                if st.session_state.role == 'editor':
                    if st.button("Edit Project", key=f"edit_{row['id']}"):
                        st.info("Edit modal would appear here.") # Placeholder for modal
                
                st.write(f"**POC:** {row.get('mainPoc', 'N/A')}")
                st.write(f"**Region:** {row.get('region', 'N/A')}")
                
                st.write("**Quantities:**")
                quantities = row.get('quantities', {})
                if isinstance(quantities, dict):
                    for item, values in quantities.items():
                        st.write(f"- {item.replace('_', ' ').title()}: {values.get('qty', 0)} {'(Bundled)' if values.get('bundled') else ''}")
                
                st.write("**Comments:**")
                comments = fetch_comments(row['id'])
                for c in comments:
                    st.text(f"[{c.get('timestamp', '...')}] {c.get('user', '')}: {c.get('text', '')}")

                with st.form(key=f"comment_form_{row['id']}"):
                    comment_text = st.text_input("Add your comment")
                    if st.form_submit_button("Post Comment"):
                        db.collection("projects").document(row['id']).collection("comments").add({
                            'text': comment_text,
                            'user': st.session_state.user_email,
                            'timestamp': firestore.SERVER_TIMESTAMP
                        })
                        db.collection("projects").document(row['id']).update({'lastActivity': firestore.SERVER_TIMESTAMP})
                        st.cache_data.clear()
                        st.rerun()

    with npi_tab:
        render_project_page("NPI", projects_df[projects_df['isNPI'] == "Yes"] if not projects_df.empty else pd.DataFrame())

    with retrofit_tab:
        render_project_page("Retrofit", projects_df[projects_df['isNPI'] == "No"] if not projects_df.empty else pd.DataFrame())

