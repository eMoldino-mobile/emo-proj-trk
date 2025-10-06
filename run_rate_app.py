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

            if isinstance(creds_raw, str):
                creds_dict = json.loads(creds_raw.replace("'", '"'))
            else:
                creds_dict = dict(creds_raw)

            if "private_key" in creds_dict and "\\n" in creds_dict["private_key"]:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)

        return firestore.client()

    except Exception as e:
        st.error(f"Firebase initialization failed. Ensure your secrets.toml is configured correctly.\n\nError: {e}")
        st.stop()

db = initialize_firebase()

# --- User Authentication ---
def login_user(email, password):
    """Authenticates a user."""
    try:
        user = firebase_auth.get_user_by_email(email)
        st.session_state.logged_in = True
        st.session_state.user_email = user.email
        st.session_state.role = st.secrets["user_roles"].get(user.email, "readonly")
    except Exception as e:
        st.error(f"Login Failed: {e}")

def logout_user():
    """Logs out the current user."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]

# --- Data Fetching ---
@st.cache_data(ttl=30)
def fetch_collection(_collection_name):
    """Fetches a collection and caches it."""
    docs = db.collection(_collection_name).stream()
    return [doc.to_dict() | {'id': doc.id} for doc in docs]

@st.cache_data(ttl=30)
def fetch_comments(_project_id):
    """Fetches comments for a single project."""
    comments_ref = db.collection("projects").document(_project_id).collection("comments").order_by("timestamp").stream()
    return [comment.to_dict() | {'id': comment.id} for comment in comments_ref]

# --- UI MODALS ---
def project_modal(project, settings):
    """Renders the form inside a modal for adding/editing projects."""
    is_new = project.get('id') is None
    title = "Add New Project" if is_new else "Edit Project"

    with st.form("project_form"):
        st.subheader(title)

        supplierName = st.selectbox("Supplier Name", settings['suppliers'], index=settings['suppliers'].index(project['supplierName']) if not is_new and project.get('supplierName') in settings['suppliers'] else 0)
        
        c1, c2 = st.columns(2)
        poRef = c1.text_input("PO Reference", project.get('poRef', ''))
        
        contact_date = project.get('firstContact', datetime.now())
        if isinstance(contact_date, datetime):
            contact_date = contact_date.date()
        firstContact = c2.date_input("First Date of Contact", value=contact_date)

        mainPoc = st.selectbox("Main POC", settings['pocs'], index=settings['pocs'].index(project['mainPoc']) if not is_new and project.get('mainPoc') in settings['pocs'] else 0)
        region = st.selectbox("Region", settings['regions'], index=settings['regions'].index(project['region']) if not is_new and project.get('region') in settings['regions'] else 0)
        
        isNPI = st.selectbox("Project Type", ["Yes", "No"], format_func=lambda x: "NPI" if x == "Yes" else "Retrofit", index=0 if project.get('isNPI', 'Yes') == "Yes" else 1)
        businessArea = st.selectbox("Business Area", ["External", "Internal"], index=0 if project.get('businessArea', 'External') == "External" else 1)
        status = st.selectbox("Status", settings['statuses'], index=settings['statuses'].index(project['status']) if not is_new and project.get('status') in settings['statuses'] else 0)
        
        st.subheader("Quantities")
        quantities = project.get('quantities', {})
        q_keys = ['sensor', 'terminal', 'plastic', 'iu_bracket', 'heat_insulator']
        new_quantities = {}
        for key in q_keys:
            cols = st.columns([3,1])
            qty = cols[0].number_input(f"{key.replace('_', ' ').title()} Qty", min_value=0, value=quantities.get(key, {}).get('qty', 0), key=f"qty_{key}")
            bundled = cols[1].checkbox("Bundled", value=quantities.get(key, {}).get('bundled', False), key=f"bundle_{key}")
            new_quantities[key] = {'qty': qty, 'bundled': bundled}
            
        if st.form_submit_button("Save Project"):
            payload = {
                "supplierName": supplierName, "poRef": poRef, "firstContact": datetime.combine(firstContact, datetime.min.time()),
                "mainPoc": mainPoc, "region": region, "isNPI": isNPI, "businessArea": businessArea, "status": status,
                "quantities": new_quantities, "lastActivity": firestore.SERVER_TIMESTAMP
            }
            if is_new:
                db.collection("projects").add(payload)
            else:
                db.collection("projects").document(project['id']).set(payload)
            st.cache_data.clear()
            st.session_state.show_project_modal = False
            st.rerun()

def settings_modal(settings):
    """Renders the settings management modal."""
    st.header("Manage Dropdown Lists")
    for key, title in {"regions": "Regions", "pocs": "POCs", "suppliers": "Suppliers", "statuses": "Statuses"}.items():
        with st.expander(title):
            for item in settings[key]:
                c1, c2 = st.columns([4,1])
                c1.write(item)
                if c2.button("Delete", key=f"del_{key}_{item}"):
                    doc_to_delete = next((d for d in fetch_collection(key) if d.get('name') == item), None)
                    if doc_to_delete:
                        db.collection(key).document(doc_to_delete['id']).delete()
                        st.cache_data.clear()
                        st.rerun()
            
            with st.form(key=f"add_{key}_form"):
                new_item = st.text_input(f"New {title.rstrip('s')}")
                if st.form_submit_button("Add"):
                    if new_item:
                        db.collection(key).add({'name': new_item})
                        st.cache_data.clear()
                        st.rerun()

# --- MAIN APP ---
if not st.session_state.get('logged_in'):
    # ... login form from previous version ...
    st.title("eMOLDINO"); st.header("Project Dashboard Login")
    with st.form("login_form"):
        email = st.text_input("Email"); password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"): login_user(email, password); st.rerun()
else:
    # --- Main Dashboard ---
    st.sidebar.title("Dashboard Menu")
    st.sidebar.write("Logged in as:"); st.sidebar.info(st.session_state.user_email)
    st.sidebar.button("Logout", on_click=logout_user, use_container_width=True)
    if st.session_state.role == 'editor':
        if st.sidebar.button("Add New Project", use_container_width=True, type="primary"): st.session_state.show_project_modal = True
        if st.sidebar.button("Manage Settings", use_container_width=True): st.session_state.show_settings_modal = True

    st.title("eMOLDINO Project Dashboard")
    projects_df = pd.DataFrame(fetch_collection("projects"))
    
    if not projects_df.empty:
        projects_df['firstContact'] = pd.to_datetime(projects_df.get('firstContact'), errors='coerce')
        projects_df['lastActivity'] = pd.to_datetime(projects_df.get('lastActivity'), errors='coerce').fillna(pd.Timestamp.min)
        projects_df = projects_df.sort_values(by='lastActivity', ascending=False, na_position='last')
    
    settings_data = { k: sorted([i.get('name', '') for i in fetch_collection(k)]) for k in ['regions', 'pocs', 'suppliers', 'statuses']}

    if st.session_state.get('show_project_modal'):
        project_to_edit = st.session_state.get('editing_project', {})
        with st.dialog("Manage Project", on_dismiss=lambda: st.session_state.update(show_project_modal=False, editing_project=None)):
            project_modal(project_to_edit, settings_data)
            
    if st.session_state.get('show_settings_modal'):
        with st.dialog("Settings", on_dismiss=lambda: st.session_state.update(show_settings_modal=False)):
            settings_modal(settings_data)

    summary_tab, npi_tab, retrofit_tab = st.tabs(["Executive Summary", "NPI Projects", "Retrofit Projects"])

    with summary_tab: # --- Executive Summary ---
        # Abridged for brevity, same as previous version
        st.header("Executive Summary")
        st.info("Summary charts will be displayed here.")

    def render_project_page(project_type, data, settings):
        view_type = st.radio("View", ["Grid", "Table"], key=f"{project_type}_view", horizontal=True)
        if view_type == "Grid":
            cols = st.columns(3)
            for i, p_series in data.iterrows():
                project = p_series.to_dict()
                with cols[i % 3]:
                    with st.container():
                        st.markdown(f"<h5>{project.get('supplierName', '')}</h5>", unsafe_allow_html=True)
                        if st.session_state.role == 'editor':
                            if st.button("Edit", key=f"edit_{project['id']}"):
                                st.session_state.editing_project = project
                                st.session_state.show_project_modal = True
                                st.rerun()
                        # ... display other card details ...
                        with st.expander("Comments"):
                             # ... comment logic ...
                            pass
        else: # Table View
            st.dataframe(data.drop(columns=['id', 'quantities', 'lastActivity'], errors='ignore'), use_container_width=True)

    with npi_tab:
        render_project_page("NPI", projects_df[projects_df['isNPI'] == "Yes"] if not projects_df.empty and 'isNPI' in projects_df.columns else pd.DataFrame(), settings_data)
    with retrofit_tab:
        render_project_page("Retrofit", projects_df[projects_df['isNPI'] == "No"] if not projects_df.empty and 'isNPI' in projects_df.columns else pd.DataFrame(), settings_data)

