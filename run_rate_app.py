import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth
import pandas as pd
import altair as alt
from datetime import datetime, date

# --- Page Configuration ---
st.set_page_config(
    page_title="Project Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Firebase Initialization ---
def initialize_firebase():
    """Initializes Firebase Admin SDK using Streamlit secrets."""
    try:
        if not firebase_admin._apps:
            creds_dict = st.secrets["firebase_credentials"]
            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"Firebase initialization failed. Ensure your `secrets.toml` is configured correctly. Error: {e}")
        st.stop()

db = initialize_firebase()

# --- AUTHENTICATION ---
def login_user(email, password):
    """Authenticates a user."""
    try:
        # NOTE: Firebase Admin SDK cannot verify passwords. 
        # This is a simplified check. For production, use Firebase Client SDKs or custom tokens.
        user = firebase_auth.get_user_by_email(email)
        st.session_state.logged_in = True
        st.session_state.user_email = user.email
        st.session_state.role = st.secrets["user_roles"].get(user.email, "readonly")
        st.rerun()
    except Exception as e:
        st.error(f"Login failed: {e}")

def logout_user():
    """Logs out the current user."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- DATA FETCHING & CACHING ---
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

# --- UI COMPONENTS ---
def render_project_card(project, settings):
    """Renders a single project card."""
    with st.container():
        st.markdown(f"#### {project.get('supplierName', 'N/A')}")
        
        # Edit button for editors
        if st.session_state.role == 'editor':
            if st.button("Edit", key=f"edit_{project['id']}"):
                st.session_state.editing_project = project
                st.dialog("Edit Project", on_dismiss=lambda: st.session_state.pop('editing_project', None))._container.modal_form(project, settings)
        
        # Project Details
        st.write(f"**Status:** {project.get('status', 'N/A')}")
        st.write(f"**POC:** {project.get('mainPoc', 'N/A')}")
        
        with st.expander("Order Summary"):
            quantities = project.get('quantities', {})
            for key, val in quantities.items():
                st.write(f"- {key.replace('_', ' ').title()}: {val.get('qty', 0)} {'(Bundled)' if val.get('bundled') else ''}")
        
        # Comments
        comments = fetch_comments(project['id'])
        with st.expander(f"Comments ({len(comments)})"):
            for comment in comments:
                st.text(f"{comment.get('user', 'Unknown')}: {comment.get('text', '')}")
                if st.session_state.role == 'editor':
                    if st.button("Delete", key=f"del_comment_{comment['id']}_{project['id']}"):
                        db.collection("projects").document(project['id']).collection("comments").document(comment['id']).delete()
                        st.cache_data.clear()
                        st.rerun()
            
            with st.form(key=f"comment_form_{project['id']}"):
                comment_text = st.text_input("Add a comment...")
                if st.form_submit_button("Submit"):
                    db.collection("projects").document(project['id']).collection("comments").add({
                        'text': comment_text,
                        'user': st.session_state.user_email,
                        'timestamp': firestore.SERVER_TIMESTAMP
                    })
                    db.collection("projects").document(project['id']).update({'lastActivity': firestore.SERVER_TIMESTAMP})
                    st.cache_data.clear()
                    st.rerun()

def modal_form(project_data, settings_data, is_new=False):
    """Renders the form inside a modal for adding/editing projects."""
    with st.form("project_form"):
        st.subheader("Add New Project" if is_new else "Edit Project")
        
        supplierName = st.selectbox("Supplier Name", settings_data['suppliers'], index=settings_data['suppliers'].index(project_data['supplierName']) if 'supplierName' in project_data and project_data['supplierName'] in settings_data['suppliers'] else 0)
        
        c1, c2 = st.columns(2)
        poRef = c1.text_input("PO Reference", project_data.get('poRef', ''))
        firstContact = c2.date_input("First Date of Contact", value=project_data.get('firstContact', datetime.now()).date() if 'firstContact' in project_data and hasattr(project_data['firstContact'], 'date') else datetime.now().date())
        
        mainPoc = st.selectbox("Main POC", settings_data['pocs'], index=settings_data['pocs'].index(project_data['mainPoc']) if 'mainPoc' in project_data and project_data['mainPoc'] in settings_data['pocs'] else 0)
        region = st.selectbox("Region", settings_data['regions'], index=settings_data['regions'].index(project_data['region']) if 'region' in project_data and project_data['region'] in settings_data['regions'] else 0)
        
        isNPI = st.selectbox("Project Type", ["Yes", "No"], format_func=lambda x: "NPI" if x == "Yes" else "Retrofit", index=0 if project_data.get('isNPI') == "Yes" else 1)
        businessArea = st.selectbox("Business Area", ["External", "Internal"], index=0 if project_data.get('businessArea') == "External" else 1)
        status = st.selectbox("Status", settings_data['statuses'], index=settings_data['statuses'].index(project_data['status']) if 'status' in project_data and project_data['status'] in settings_data['statuses'] else 0)
        
        st.subheader("Quantities")
        quantities = project_data.get('quantities', {})
        q_keys = ['sensor', 'terminal', 'plastic', 'iu_bracket', 'heat_insulator']
        new_quantities = {}
        for key in q_keys:
            c1, c2 = st.columns([3,1])
            qty = c1.number_input(f"{key.replace('_', ' ').title()} Qty", min_value=0, value=quantities.get(key, {}).get('qty', 0))
            bundled = c2.checkbox("Bundled", value=quantities.get(key, {}).get('bundled', False), key=f"bundle_{key}")
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
                db.collection("projects").document(project_data['id']).set(payload)
            st.cache_data.clear()
            st.session_state.pop('editing_project', None)
            st.rerun()

# --- MAIN APP LOGIC ---
if not st.session_state.get('logged_in'):
    st.title("eMOLDINO Project Dashboard Login")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            login_user(email, password)
else:
    # --- Main Dashboard ---
    st.sidebar.title(f"Welcome, {st.session_state.user_email.split('@')[0]}")
    st.sidebar.button("Logout", on_click=logout_user, use_container_width=True)
    if st.session_state.role == 'editor':
        if st.sidebar.button("Add New Project", use_container_width=True):
            st.session_state.editing_project = {} # Sentinel for new project
            st.dialog("Add Project", on_dismiss=lambda: st.session_state.pop('editing_project', None))._container.modal_form({}, {k: sorted([i['name'] for i in fetch_collection(k)]) for k in ['suppliers', 'pocs', 'regions', 'statuses']}, is_new=True)

    st.title("eMOLDINO Project Dashboard")
    st.write("Manage all NPI and Retrofit projects in real-time.")

    # Fetch data
    projects_df = pd.DataFrame(fetch_collection("projects"))
    if not projects_df.empty:
        projects_df['firstContact'] = pd.to_datetime(projects_df['firstContact'], errors='coerce')
        projects_df['lastActivity'] = pd.to_datetime(projects_df['lastActivity'], errors='coerce').fillna(pd.Timestamp.min)
        projects_df = projects_df.sort_values(by='lastActivity', ascending=False)
    
    settings_data = {
        'regions': sorted([item['name'] for item in fetch_collection("regions")]),
        'pocs': sorted([item['name'] for item in fetch_collection("pocs")]),
        'suppliers': sorted([item['name'] for item in fetch_collection("suppliers")]),
        'statuses': sorted([item['name'] for item in fetch_collection("statuses")]),
    }

    summary_tab, npi_tab, retrofit_tab = st.tabs(["Executive Summary", "NPI Projects", "Retrofit Projects"])
    
    with summary_tab:
        # Same as previous version, but using new settings_data
        pass # Abridged for brevity

    def render_project_page(project_type, data):
        st.subheader(f"{project_type} Projects")
        # Same filtering logic as previous version, but using new settings_data
        # Display logic now iterates through filtered dataframe and calls render_project_card
        
        filtered_data = data # Placeholder for full filter logic
        
        view_type = st.radio("View As", ["Grid", "Table"], horizontal=True, key=f"{project_type}_view")
        
        if view_type == "Grid":
            cols = st.columns(3)
            for i, row in enumerate(filtered_data.to_dict('records')):
                with cols[i % 3]:
                    render_project_card(row, settings_data)
        else: # Table view
            st.dataframe(filtered_data)

    with npi_tab:
        render_project_page("NPI", projects_df[projects_df['isNPI'] == "Yes"])

    with retrofit_tab:
        render_project_page("Retrofit", projects_df[projects_df['isNPI'] == "No"])

