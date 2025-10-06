import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth
import pandas as pd
import altair as alt
from datetime import datetime, date
import json

# --- Page Configuration ---
st.set_page_config(
    page_title="eMOLDINO Project Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Custom Styling ---
st.markdown("""
<style>
    /* General Dark Theme */
    [data-testid="stAppViewContainer"] {
        background-color: #111827; /* bg-gray-900 */
    }
    [data-testid="stHeader"] {
        background-color: #111827;
    }
    [data-testid="stToolbar"] {
        right: 2rem;
    }
    .st-emotion-cache-16txtl3 {
        padding-top: 2rem;
    }
    h1, h2, h3, h4 {
        color: #f9fafb; /* text-gray-50 */
    }
    p, .st-emotion-cache-1r4qj8v {
        color: #d1d5db; /* text-gray-300 */
    }

    /* Login Form */
    .login-container {
        background-color: #1e293b; /* bg-slate-800 */
        padding: 2rem;
        border-radius: 0.75rem;
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        max-width: 450px;
        margin: auto;
    }
    
    /* Buttons */
    .stButton>button {
        border-color: #3b82f6; /* blue-500 */
        background-color: #3b82f6;
        color: white;
    }
    .stButton>button:hover {
        border-color: #2563eb; /* blue-600 */
        background-color: #2563eb;
    }
    
    /* Project Cards */
    [data-testid="stVerticalBlock"] .st-emotion-cache-1xarl3l {
        background-color: #1f2937; /* bg-gray-800 */
        border: 1px solid #374151; /* border-gray-700 */
        border-radius: 0.5rem;
        padding: 1rem;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: transparent;
        border-bottom: 3px solid #3b82f6;
    }
    
    /* Dataframe */
    [data-testid="stDataFrame"] {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)


# --- Firebase Initialization ---
def initialize_firebase():
    """Initializes Firebase Admin SDK using Streamlit secrets."""
    try:
        if not firebase_admin._apps:
            creds_raw = st.secrets["firebase_credentials"]
            if isinstance(creds_raw, str):
                creds_dict = json.loads(creds_raw)
            else:
                creds_dict = dict(creds_raw)
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            
            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"Firebase initialization failed. Ensure your secrets.toml is correct. Error: {e}")
        st.stop()

db = initialize_firebase()

# --- User Authentication ---
def login_user(email, password):
    """Logs in the user and sets session state."""
    try:
        user = firebase_auth.get_user_by_email(email)
        # Mock verification for demonstration. In a real app, you'd handle password verification.
        st.session_state.logged_in = True
        st.session_state.user_email = user.email
        st.session_state.role = st.secrets["user_roles"].get(user.email, "readonly")
        st.rerun()
    except Exception as e:
        st.error(f"Login Failed: {e}")

def logout_user():
    """Logs out the user by clearing the session state."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- Data Fetching (Cached) ---
@st.cache_data(ttl=60)
def fetch_collection(_collection_name):
    """Fetches all documents from a Firestore collection."""
    docs = db.collection(_collection_name).stream()
    return [doc.to_dict() | {'id': doc.id} for doc in docs]

@st.cache_data(ttl=30)
def fetch_comments(_project_id):
    """Fetches all comments for a specific project, ordered by timestamp."""
    comments_ref = db.collection("projects").document(_project_id).collection("comments").order_by("timestamp").stream()
    return [comment.to_dict() | {'id': comment.id} for comment in comments_ref]

# --- UI MODALS & DIALOGS ---
def project_dialog(project_data, settings_data):
    """Renders the Add/Edit Project form content."""
    is_new = project_data.get('id') is None
    title = "Add New Project" if is_new else "Edit Project"

    with st.form("project_form"):
        st.subheader(title)
        
        is_disabled = st.session_state.role == 'readonly'
        
        supplierName = st.selectbox(
            "Supplier Name", settings_data['suppliers'], 
            index=settings_data['suppliers'].index(project_data['supplierName']) if not is_new and project_data.get('supplierName') in settings_data['suppliers'] else 0,
            disabled=is_disabled
        )
        c1, c2 = st.columns(2)
        poRef = c1.text_input("PO Reference", project_data.get('poRef', ''), disabled=is_disabled)
        
        contact_date = project_data.get('firstContact')
        if isinstance(contact_date, datetime):
            contact_val = contact_date.date()
        elif isinstance(contact_date, date):
            contact_val = contact_date
        else:
            contact_val = datetime.now().date()
        
        firstContact = c2.date_input("First Date of Contact", value=contact_val, disabled=is_disabled)

        mainPoc = st.selectbox("Main POC", settings_data['pocs'], index=settings_data['pocs'].index(project_data['mainPoc']) if not is_new and project_data.get('mainPoc') in settings_data['pocs'] else 0, disabled=is_disabled)
        region = st.selectbox("Region", settings_data['regions'], index=settings_data['regions'].index(project_data['region']) if not is_new and project_data.get('region') in settings_data['regions'] else 0, disabled=is_disabled)
        
        c3, c4 = st.columns(2)
        isNPI = c3.selectbox("Project Type", ["Yes", "No"], format_func=lambda x: "NPI" if x == "Yes" else "Retrofit", index=0 if project_data.get('isNPI', 'Yes') == "Yes" else 1, disabled=is_disabled)
        businessArea = c4.selectbox("Business Area", ["External", "Internal"], index=0 if project_data.get('businessArea', 'External') == "External" else 1, disabled=is_disabled)

        status = st.selectbox("Status", settings_data['statuses'], index=settings_data['statuses'].index(project_data['status']) if not is_new and project_data.get('status') in settings_data['statuses'] else 0, disabled=is_disabled)
        
        st.subheader("Quantities")
        quantities = project_data.get('quantities', {})
        q_keys = ['sensor', 'terminal', 'plastic', 'iu_bracket', 'heat_insulator']
        new_quantities = {}
        for key in q_keys:
            cols = st.columns([3, 1])
            qty = cols[0].number_input(f"{key.replace('_', ' ').title()} Qty", min_value=0, value=quantities.get(key, {}).get('qty', 0), key=f"qty_{key}", disabled=is_disabled)
            bundled = cols[1].checkbox("Bundled", value=quantities.get(key, {}).get('bundled', False), key=f"bundle_{key}", disabled=is_disabled)
            new_quantities[key] = {'qty': qty, 'bundled': bundled}
            
        if not is_disabled:
            if st.form_submit_button("Save Project", use_container_width=True, type="primary"):
                firstContact_dt = datetime.combine(firstContact, datetime.min.time())
                payload = {"supplierName": supplierName, "poRef": poRef, "firstContact": firstContact_dt, "mainPoc": mainPoc, "region": region, "isNPI": isNPI, "businessArea": businessArea, "status": status, "quantities": new_quantities, "lastActivity": firestore.SERVER_TIMESTAMP}
                try:
                    if is_new:
                        db.collection("projects").add(payload)
                        st.toast("✅ Project added successfully!")
                    else:
                        db.collection("projects").document(project_data['id']).set(payload, merge=True)
                        st.toast("✅ Project updated successfully!")
                    
                    st.session_state.show_project_dialog = False
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving project: {e}")

    if not is_new:
        st.markdown("---")
        st.subheader("Comments")
        comments = fetch_comments(project_data['id'])
        with st.container(height=200):
            for c in reversed(comments):
                timestamp_str = c.get('timestamp', datetime.now()).strftime('%Y-%m-%d %H:%M')
                user_str = c.get('user', '...').split('@')[0]
                st.markdown(f"**{user_str}** <small>({timestamp_str})</small>: {c.get('text', '')}", unsafe_allow_html=True)
        
        with st.form(key="dialog_comment_form"):
            new_comment = st.text_input("Add a comment", label_visibility="collapsed", placeholder="Add a comment...")
            if st.form_submit_button("Post", use_container_width=True):
                if new_comment:
                    db.collection("projects").document(project_data['id']).collection("comments").add({'text': new_comment, 'user': st.session_state.user_email, 'timestamp': firestore.SERVER_TIMESTAMP})
                    db.collection("projects").document(project_data['id']).update({'lastActivity': firestore.SERVER_TIMESTAMP})
                    st.cache_data.clear()
                    st.rerun()

def settings_dialog(settings):
    """Renders the settings management content."""
    cols = st.columns(4)
    setting_map = {"suppliers": "Suppliers", "statuses": "Statuses", "regions": "Regions", "pocs": "POCs"}
    
    for i, (key, title) in enumerate(setting_map.items()):
        with cols[i]:
            st.subheader(title)
            for item in settings[key]:
                c1, c2 = st.columns([4, 1])
                c1.write(item)
                if c2.button("🗑️", key=f"del_{key}_{item}", help=f"Delete {item}"):
                    doc_to_delete = next((d for d in fetch_collection(key) if d.get('name') == item), None)
                    if doc_to_delete:
                        db.collection(key).document(doc_to_delete['id']).delete()
                        st.cache_data.clear()
                        st.rerun()
            
            with st.form(key=f"add_{key}_form"):
                new_item = st.text_input(f"New {title.rstrip('s')}", label_visibility="collapsed", placeholder=f"New {title.rstrip('s')}")
                if st.form_submit_button("Add") and new_item:
                    db.collection(key).add({'name': new_item})
                    st.cache_data.clear()
                    st.rerun()

# --- Charting Functions ---
def create_chart(data, x_col, y_col, title, chart_type='bar'):
    """Helper function to create an Altair chart."""
    if chart_type == 'bar':
        chart = alt.Chart(data).mark_bar().encode(
            x=alt.X(f'{x_col}:N', sort='-y', title=None),
            y=alt.Y(f'{y_col}:Q', title=None),
            tooltip=[x_col, y_col]
        )
    elif chart_type == 'line':
        chart = alt.Chart(data).mark_line(point=True).encode(
            x=alt.X(f'{x_col}:O', title=None),
            y=alt.Y(f'{y_col}:Q', title=None),
            tooltip=[x_col, y_col]
        )
    elif chart_type == 'donut':
        chart = alt.Chart(data).mark_arc(innerRadius=50).encode(
            theta=alt.Theta(field=y_col, type="quantitative"),
            color=alt.Color(field=x_col, type="nominal", title=None),
            tooltip=[x_col, y_col]
        )
    return chart.properties(title=title, background='transparent').configure_view(strokeOpacity=0).configure_title(
        anchor='start', color='#f9fafb'
    ).configure_axis(
        labelColor='#d1d5db', titleColor='#d1d5db', gridColor='#374151', domainColor='#374151'
    ).configure_legend(
        labelColor='#d1d5db', titleColor='#d1d5db'
    )

# --- MAIN APP LOGIC ---
if not st.session_state.get('logged_in'):
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.title("eMOLDINO")
    st.header("Project Dashboard Login")
    with st.form("login_form"):
        email = st.text_input("📧 Email")
        password = st.text_input("🔒 Password", type="password")
        if st.form_submit_button("Login", use_container_width=True):
            login_user(email, password)
    st.markdown('</div>', unsafe_allow_html=True)
else:
    # Fetch all data once
    projects_df = pd.DataFrame(fetch_collection("projects"))
    if not projects_df.empty:
        projects_df['firstContact'] = pd.to_datetime(projects_df['firstContact'], errors='coerce')
        projects_df['lastActivity'] = pd.to_datetime(projects_df['lastActivity'], errors='coerce')
        projects_df = projects_df.sort_values(by='lastActivity', ascending=False, na_position='last')
    
    settings_data = {k: sorted([i.get('name', '') for i in fetch_collection(k)]) for k in ['regions', 'pocs', 'suppliers', 'statuses']}

    # --- Header ---
    header_cols = st.columns([3, 1, 1, 2])
    with header_cols[0]:
        st.title("eMOLDINO Dashboard")
        st.caption("Manage all NPI and Retrofit projects in real-time.")
    
    if st.session_state.role == 'editor':
        if header_cols[1].button("➕ Add New Project", use_container_width=True):
            st.session_state.update(show_project_dialog=True, editing_project={})
        if header_cols[2].button("⚙️ Settings", use_container_width=True):
            st.session_state.show_settings_dialog = True
            
    with header_cols[3]:
        st.markdown(f"<div style='text-align: right;'>Logged in as:<br><b>{st.session_state.user_email}</b></div>", unsafe_allow_html=True)
        if st.button("Logout", use_container_width=True):
            logout_user()
    
    st.markdown("---")

    # --- MODAL/DIALOG REPLACEMENT (STABLE FIX) ---
    # This block replaces the st.dialog() calls with a conditional rendering pattern
    if st.session_state.get('show_project_dialog'):
        with st.container(border=True):
            project_dialog(st.session_state.get('editing_project', {}), settings_data)
            if st.button("Close Window", key="close_project"):
                st.session_state.show_project_dialog = False
                st.rerun()
    elif st.session_state.get('show_settings_dialog'):
        with st.container(border=True):
            st.markdown("### ⚙️ Settings")
            settings_dialog(settings_data)
            if st.button("Close Settings", key="close_settings"):
                st.session_state.show_settings_dialog = False
                st.rerun()
    else:
        # --- Main Content Tabs (only show if no "dialog" is open) ---
        summary_tab, npi_tab, retrofit_tab = st.tabs(["Executive Summary", "NPI Projects", "Retrofit Projects"])

        with summary_tab:
            st.header("Executive Summary")
            if not projects_df.empty:
                summary_df = projects_df.copy()
                summary_df['sensor_qty'] = summary_df['quantities'].apply(lambda q: q.get('sensor', {}).get('qty', 0) if isinstance(q, dict) else 0)

                business_filter = st.radio("Filter by Business Area", ["All", "External", "Internal"], horizontal=True, key="summary_business_filter")
                
                if business_filter != "All":
                    summary_df = summary_df[summary_df['businessArea'] == business_filter]
                    
                c1, c2 = st.columns(2)
                with c1:
                    sensors_by_region = summary_df.groupby('region')['sensor_qty'].sum().reset_index()
                    st.altair_chart(create_chart(sensors_by_region, 'region', 'sensor_qty', 'Total Sensors by Region'), use_container_width=True)
                    
                    new_projects = summary_df.copy()
                    new_projects['quarter'] = new_projects['firstContact'].dt.to_period('Q').astype(str)
                    projects_by_quarter = new_projects.groupby('quarter').size().reset_index(name='count')
                    st.altair_chart(create_chart(projects_by_quarter, 'quarter', 'count', 'New Projects by Quarter', 'line'), use_container_width=True)

                with c2:
                    status_counts = summary_df['status'].value_counts().reset_index()
                    status_counts.columns = ['status', 'count']
                    st.altair_chart(create_chart(status_counts, 'status', 'count', 'Project Status Overview', 'donut'), use_container_width=True)
                    
                    workload_by_poc = summary_df['mainPoc'].value_counts().reset_index()
                    workload_by_poc.columns = ['mainPoc', 'count']
                    st.altair_chart(create_chart(workload_by_poc, 'mainPoc', 'count', 'Workload by POC'), use_container_width=True)
            else:
                st.info("No project data to display.")

        def render_project_page(project_type, data):
            with st.expander("🔍 Filters"):
                f_cols = st.columns([2, 2, 2, 1])
                region_filter = f_cols[0].selectbox("Region", ["All"] + settings_data['regions'], key=f"{project_type}_region")
                poc_filter = f_cols[1].selectbox("POC", ["All"] + settings_data['pocs'], key=f"{project_type}_poc")
                
                pricing_filter_options = {"All": "All", "Bundled": True, "Not Bundled": False}
                pricing_filter = f_cols[2].radio("Pricing", pricing_filter_options.keys(), horizontal=True, key=f"{project_type}_pricing")

                filtered_data = data.copy()
                if region_filter != "All":
                    filtered_data = filtered_data[filtered_data['region'] == region_filter]
                if poc_filter != "All":
                    filtered_data = filtered_data[filtered_data['mainPoc'] == poc_filter]
                if pricing_filter != "All":
                    filtered_data['has_bundled'] = filtered_data['quantities'].apply(
                        lambda q: any(item.get('bundled', False) for item in q.values()) if isinstance(q, dict) else False
                    )
                    filtered_data = filtered_data[filtered_data['has_bundled'] == pricing_filter_options[pricing_filter]]
            
            v_cols = st.columns([3, 1, 1])
            business_area_filter = v_cols[0].radio("Business Area", ["All", "External", "Internal"], horizontal=True, key=f"{project_type}_business")
            if business_area_filter != "All":
                filtered_data = filtered_data[filtered_data['businessArea'] == business_area_filter]
                
            view_type = v_cols[1].radio("View As", ["Grid", "Table"], horizontal=True, key=f"{project_type}_view")

            csv = filtered_data.to_csv(index=False).encode('utf-8')
            v_cols[2].download_button(
                label="📥 Export CSV",
                data=csv,
                file_name=f'{project_type}_projects.csv',
                mime='text/csv',
                use_container_width=True
            )
            st.markdown("---")

            if filtered_data.empty:
                st.info("No projects match the current filters.")
                return

            if view_type == "Grid":
                cols = st.columns(3)
                for i, p_series in filtered_data.iterrows():
                    with cols[i % 3]:
                        with st.container(border=True):
                            c1, c2 = st.columns([4, 1])
                            c1.markdown(f"**{p_series.get('supplierName', 'N/A')}**")
                            if st.session_state.role == 'editor':
                               if c2.button("✏️", key=f"edit_grid_{p_series['id']}", help="Edit Project"):
                                    st.session_state.editing_project = p_series.to_dict()
                                    st.session_state.show_project_dialog = True
                                    st.rerun()

                            st.info(f"Status: {p_series.get('status', 'N/A')}")
                            st.write(f"POC: {p_series.get('mainPoc', 'N/A')}")
                            
                            comments = fetch_comments(p_series['id'])
                            with st.expander(f"Comments ({len(comments)})"):
                                if comments:
                                    for c in sorted(comments, key=lambda x: x['timestamp'], reverse=True)[:3]:
                                        st.text(f"{c.get('user', '...').split('@')[0]}: {c.get('text', '')}")
                                else:
                                    st.write("No comments yet.")
                                    
            else: # Table View
                header_cols = st.columns([3, 2, 2, 2, 1])
                headers = ["Supplier", "Status", "POC", "Region", "Actions"]
                for col, header in zip(header_cols, headers):
                    col.markdown(f"**{header}**")
                
                st.markdown("<hr style='margin-top: 0; margin-bottom: 0.5rem;'>", unsafe_allow_html=True)
                
                for i, row in filtered_data.iterrows():
                    row_cols = st.columns([3, 2, 2, 2, 1])
                    row_cols[0].write(row.get('supplierName', 'N/A'))
                    row_cols[1].write(row.get('status', 'N/A'))
                    row_cols[2].write(row.get('mainPoc', 'N/A'))
                    row_cols[3].write(row.get('region', 'N/A'))
                    
                    if row_cols[4].button("View/Edit", key=f"edit_table_{row['id']}", use_container_width=True):
                        st.session_state.editing_project = row.to_dict()
                        st.session_state.show_project_dialog = True
                        st.rerun()
                    st.markdown("<hr style='margin-top: 0.5rem; margin-bottom: 0.5rem;'>", unsafe_allow_html=True)

        with npi_tab:
            if not projects_df.empty and 'isNPI' in projects_df.columns:
                render_project_page("NPI", projects_df[projects_df['isNPI'] == "Yes"])
            else:
                st.info("No NPI projects found.")

        with retrofit_tab:
            if not projects_df.empty and 'isNPI' in projects_df.columns:
                render_project_page("Retrofit", projects_df[projects_df['isNPI'] == "No"])
            else:
                st.info("No Retrofit projects found.")

