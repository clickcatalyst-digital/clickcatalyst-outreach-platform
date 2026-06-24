# collector_app.py
# Human-in-the-Loop Contact Entry Tool
# Run with: streamlit run app.py
#
# Workflow:
#   1. Shows next Intelligence_Ready company with no contacts yet
#   2. You research the person, enter their details
#   3. Save & Next → moves to next company
#   4. Add Another Contact → stays on same company
#   5. Skip → marks as No_Contact_Found, never shows again

# Modes:
#   1. Queue Mode  — auto-loads next company without contacts
#   2. Search Mode — manually search by CIN or company name, add contacts to any company

import sqlite3
import pandas as pd
import streamlit as st
from datetime import date

DB_PATH = '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'

JOB_TITLES = [
    'Founder',
    'Co-Founder',
    'CEO',
    'CMO',
    'Head of Marketing',
    'VP Marketing',
    'Growth Lead',
    'Digital Marketing Manager',
    'Director',
    'Other'
]

EMAIL_LABELS = [
    'Work',
    'Personal',
    'Founder',
    'Marketing',
    'Info / Generic',
    'Other'
]


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------

def ensure_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS company_contacts (
            Contact_ID          INTEGER PRIMARY KEY AUTOINCREMENT,
            CIN                 TEXT NOT NULL,
            Full_Name           TEXT NOT NULL,
            Job_Title           TEXT,
            Email_Address       TEXT NOT NULL,
            Email_Label         TEXT DEFAULT 'Work',
            LinkedIn_URL        TEXT,
            Is_Primary_Contact  BOOLEAN DEFAULT 1,
            Added_Date          DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (CIN) REFERENCES company_enrichment(CIN)
        );
    """)
    # Add Email_Label column if it doesn't exist (for existing DBs)
    try:
        cursor.execute("ALTER TABLE company_contacts ADD COLUMN Email_Label TEXT DEFAULT 'Work';")
    except sqlite3.OperationalError:
        pass
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_contacts_cin ON company_contacts (CIN);
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# QUERIES
# ---------------------------------------------------------------------------

def get_next_lead():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT
            q.CIN,
            q.CompanyName,
            e.Website_URL,
            e.Personalized_Sentence,
            e.Competitor_Count,
            e.Pipeline_Status
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE q.CIN NOT IN (
            SELECT DISTINCT CIN FROM company_contacts
        )
        LIMIT 1;
    """, conn)
    conn.close()
    return df.iloc[0].to_dict() if not df.empty else None


def search_companies(query):
    """Search by CIN or company name."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT
            q.CIN,
            q.CompanyName,
            e.Website_URL,
            e.Personalized_Sentence,
            e.Competitor_Count,
            e.Pipeline_Status
        FROM vw_qualified_leads q
        LEFT JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE q.CIN LIKE ? OR UPPER(q.CompanyName) LIKE UPPER(?)
        LIMIT 20;
    """, conn, params=(f'%{query}%', f'%{query}%'))
    conn.close()
    return df


def get_lead_by_cin(cin):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT
            q.CIN,
            q.CompanyName,
            e.Website_URL,
            e.Personalized_Sentence,
            e.Competitor_Count,
            e.Pipeline_Status
        FROM vw_qualified_leads q
        LEFT JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE q.CIN = ?
        LIMIT 1;
    """, conn, params=(cin,))
    conn.close()
    return df.iloc[0].to_dict() if not df.empty else None


def get_leads_ready_count():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT CIN) FROM company_contacts")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_queue_size():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*)
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE q.CIN NOT IN (
            SELECT DISTINCT CIN FROM company_contacts
        )
    """)
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_existing_contacts(cin):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT Contact_ID, Full_Name, Job_Title, Email_Address,
               Email_Label, LinkedIn_URL, Is_Primary_Contact
        FROM company_contacts
        WHERE CIN = ?
        ORDER BY Is_Primary_Contact DESC, Contact_ID ASC
    """, conn, params=(cin,))
    conn.close()
    return df


def save_contact(cin, full_name, job_title, email, email_label, linkedin_url, is_primary):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if is_primary:
        cursor.execute(
            "UPDATE company_contacts SET Is_Primary_Contact = 0 WHERE CIN = ?", (cin,)
        )
    cursor.execute("""
        INSERT INTO company_contacts
            (CIN, Full_Name, Job_Title, Email_Address, Email_Label,
             LinkedIn_URL, Is_Primary_Contact, Added_Date)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_DATE)
    """, (cin, full_name.strip(), job_title, email.strip(), email_label,
          linkedin_url.strip() or None, int(is_primary)))
    conn.commit()
    conn.close()


def delete_contact(contact_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM company_contacts WHERE Contact_ID = ?", (contact_id,))
    conn.commit()
    conn.close()


def set_primary_contact(contact_id, cin):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE company_contacts SET Is_Primary_Contact = 0 WHERE CIN = ?", (cin,))
    cursor.execute("UPDATE company_contacts SET Is_Primary_Contact = 1 WHERE Contact_ID = ?", (contact_id,))
    conn.commit()
    conn.close()


def skip_lead(cin):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE company_enrichment
        SET Pipeline_Status = 'No_Contact_Found'
        WHERE CIN = ?
    """, (cin,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def validate_email(email):
    return '@' in email and '.' in email.split('@')[-1]


def validate_linkedin(url):
    if not url:
        return True
    return 'linkedin.com' in url.lower()


# ---------------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------------

def init_session():
    defaults = {
        'current_lead': None,
        'stay_on_lead': False,
        'success_message': None,
        'mode': 'queue',           # 'queue' or 'search'
        'search_query': '',
        'search_results': None,
        'selected_cin': None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ---------------------------------------------------------------------------
# REUSABLE: CONTACT FORM
# ---------------------------------------------------------------------------

def render_contact_form(lead, form_key_suffix=''):
    """Renders the contact entry form for a given lead dict."""
    cin = lead['CIN']

    with st.form(key=f"contact_form_{cin}_{form_key_suffix}", clear_on_submit=True):

        col_a, col_b = st.columns(2)
        with col_a:
            first_name = st.text_input('First Name *', placeholder='Rahul')
        with col_b:
            last_name = st.text_input('Last Name *', placeholder='Sharma')

        col_c, col_d = st.columns(2)
        with col_c:
            job_title = st.selectbox('Job Title *', options=JOB_TITLES)
        with col_d:
            email_label = st.selectbox('Email Type', options=EMAIL_LABELS)

        email = st.text_input('Email Address *', placeholder='rahul@company.com')
        linkedin_url = st.text_input('LinkedIn URL (optional)', placeholder='https://linkedin.com/in/...')

        existing = get_existing_contacts(cin)
        default_primary = existing.empty
        is_primary = st.checkbox(
            '⭐ Make Primary Contact (receives the email)',
            value=default_primary
        )

        st.markdown('')
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        with btn_col1:
            save_next = st.form_submit_button('✅ Save & Next', use_container_width=True, type='primary')
        with btn_col2:
            save_stay = st.form_submit_button('➕ Add Another', use_container_width=True)
        with btn_col3:
            skip = st.form_submit_button('⏭️ Skip Company', use_container_width=True)

        # --- Skip ---
        if skip:
            skip_lead(cin)
            st.session_state.stay_on_lead = False
            st.session_state.current_lead = None
            st.session_state.selected_cin = None
            st.session_state.success_message = f"⏭️ Skipped {lead['CompanyName']}."
            st.rerun()

        # --- Save ---
        if save_next or save_stay:
            errors = []
            if not first_name.strip(): errors.append('First name is required.')
            if not last_name.strip():  errors.append('Last name is required.')
            if not email.strip():      errors.append('Email address is required.')
            elif not validate_email(email.strip()): errors.append('Email address is not valid.')
            if linkedin_url.strip() and not validate_linkedin(linkedin_url.strip()):
                errors.append('LinkedIn URL must contain linkedin.com.')

            if errors:
                for err in errors:
                    st.error(err)
            else:
                full_name = f"{first_name.strip()} {last_name.strip()}"
                save_contact(cin, full_name, job_title, email, email_label, linkedin_url, is_primary)

                if save_next:
                    st.session_state.stay_on_lead = False
                    st.session_state.current_lead = None
                    st.session_state.selected_cin = None
                    st.session_state.success_message = f"✅ Saved {full_name} for {lead['CompanyName']}."
                    st.rerun()
                elif save_stay:
                    st.session_state.stay_on_lead = True
                    st.session_state.success_message = f"✅ Saved {full_name}. Add another contact."
                    st.rerun()


# ---------------------------------------------------------------------------
# REUSABLE: COMPANY PANEL (left column)
# ---------------------------------------------------------------------------

def render_company_panel(lead):
    st.subheader('📋 Company Context')
    st.markdown(f"### {lead['CompanyName']}")
    st.caption(f"CIN: `{lead['CIN']}`")

    status = lead.get('Pipeline_Status') or '—'
    st.caption(f"Pipeline Status: `{status}`")

    with st.expander("🌐 Website" + (f": {lead['Website_URL']}" if lead.get('Website_URL') else ': Not found yet')):
        new_url = st.text_input(
            'Update website URL',
            value=lead.get('Website_URL') or '',
            key=f"website_edit_{lead['CIN']}"
        )
        if st.button('💾 Save URL', key=f"save_url_{lead['CIN']}"):
            if new_url.strip():
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE company_enrichment
                    SET Website_URL = ?, Domain_Source = 'Manual Override'
                    WHERE CIN = ?
                """, (new_url.strip(), lead['CIN']))
                conn.commit()
                conn.close()
                st.success(f"✅ Website updated to {new_url.strip()}")
                st.rerun()
            else:
                st.error('URL cannot be empty.')

    if lead.get('Competitor_Count'):
        st.markdown(f"👥 **Competitors in cohort:** {int(lead['Competitor_Count'])}")

    if lead.get('Personalized_Sentence'):
        st.markdown('---')
        st.markdown('**📨 Personalized Email Sentence:**')
        st.info(lead['Personalized_Sentence'])

    st.markdown('---')
    st.markdown('**🔍 Research Links:**')
    company_query = lead['CompanyName'].replace(' ', '+')
    st.markdown(f"- [Search LinkedIn](https://www.linkedin.com/search/results/people/?keywords={company_query})")
    if lead.get('Website_URL'):
        st.markdown(f"- [About Page]({lead['Website_URL']}/about)")
    st.markdown(f"- [Google Search](https://www.google.com/search?q={company_query}+founder+email)")

    # Existing contacts
    existing = get_existing_contacts(lead['CIN'])
    if not existing.empty:
        st.markdown('---')
        st.markdown('**👤 Saved Contacts:**')
        for _, c in existing.iterrows():
            primary_tag = ' ⭐' if c['Is_Primary_Contact'] else ''
            label_tag = f" · `{c['Email_Label']}`" if c.get('Email_Label') else ''
            st.markdown(
                f"- **{c['Full_Name']}** · {c['Job_Title']}{primary_tag}<br>"
                f"  `{c['Email_Address']}`{label_tag}",
                unsafe_allow_html=True
            )
            col_p, col_d = st.columns([1, 1])
            with col_p:
                if not c['Is_Primary_Contact']:
                    if st.button('⭐ Make Primary', key=f"primary_{c['Contact_ID']}"):
                        set_primary_contact(c['Contact_ID'], lead['CIN'])
                        st.rerun()
            with col_d:
                if st.button('🗑️ Delete', key=f"del_{c['Contact_ID']}"):
                    delete_contact(c['Contact_ID'])
                    st.rerun()


# ---------------------------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title='ClickCatalyst — Contact Entry',
        page_icon='🎯',
        layout='wide'
    )

    ensure_schema()
    init_session()

    # --- Header ---
    st.title('🎯 ClickCatalyst — Contact Entry')
    st.caption('Human-in-the-Loop · Add contacts manually to unlock email dispatch')

    # --- Metrics ---
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric('✅ Leads Ready for Email', get_leads_ready_count())
    with col_m2:
        st.metric('⏳ Remaining in Queue', get_queue_size())
    with col_m3:
        st.metric('📅 Today', date.today().strftime('%d %b %Y'))

    st.divider()

    # --- Mode Toggle ---
    mode_col1, mode_col2 = st.columns([1, 3])
    with mode_col1:
        mode = st.radio(
            'Mode',
            options=['Queue', 'Search by CIN / Name'],
            index=0 if st.session_state.mode == 'queue' else 1,
            horizontal=True
        )
        st.session_state.mode = 'queue' if mode == 'Queue' else 'search'

    st.divider()

    # --- Success message ---
    if st.session_state.success_message:
        st.success(st.session_state.success_message)
        st.session_state.success_message = None

    # ═══════════════════════════════════════
    # QUEUE MODE
    # ═══════════════════════════════════════
    if st.session_state.mode == 'queue':

        if not st.session_state.stay_on_lead or st.session_state.current_lead is None:
            st.session_state.current_lead = get_next_lead()
            st.session_state.stay_on_lead = False

        lead = st.session_state.current_lead

        if lead is None:
            st.success('🏁 Queue empty! All qualified leads have contacts assigned.')
            st.info('Run the pipeline to enrich more leads, then come back here to add contacts.')
            return

        left_col, right_col = st.columns([1, 1], gap='large')
        with left_col:
            render_company_panel(lead)
        with right_col:
            st.subheader('✏️ Add Contact')
            render_contact_form(lead, form_key_suffix='queue')

    # ═══════════════════════════════════════
    # SEARCH MODE
    # ═══════════════════════════════════════
    else:
        st.markdown('### 🔍 Search Company')

        search_col, btn_col = st.columns([4, 1])
        with search_col:
            query = st.text_input(
                'Enter CIN or company name',
                placeholder='e.g. U47910 or Zupzy',
                label_visibility='collapsed'
            )
        with btn_col:
            search_btn = st.button('Search', use_container_width=True, type='primary')

        if search_btn and query.strip():
            st.session_state.search_query = query.strip()
            st.session_state.search_results = search_companies(query.strip())
            st.session_state.selected_cin = None

        # --- Show search results ---
        if st.session_state.search_results is not None:
            df = st.session_state.search_results

            if df.empty:
                st.warning('No companies found. Try a different CIN or name.')
            else:
                st.markdown(f"**{len(df)} result(s) found** — click a row to select:")

                for _, row in df.iterrows():
                    contact_count = len(get_existing_contacts(row['CIN']))
                    label = f"{'✅ ' if contact_count > 0 else '○ '} **{row['CompanyName']}** · `{row['CIN']}` · {contact_count} contact(s)"
                    if st.button(label, key=f"select_{row['CIN']}", use_container_width=True):
                        st.session_state.selected_cin = row['CIN']
                        st.rerun()

        # --- Show selected company ---
        if st.session_state.selected_cin:
            st.divider()
            lead = get_lead_by_cin(st.session_state.selected_cin)

            if lead:
                left_col, right_col = st.columns([1, 1], gap='large')
                with left_col:
                    render_company_panel(lead)
                with right_col:
                    st.subheader('✏️ Add Contact')
                    render_contact_form(lead, form_key_suffix='search')
            else:
                st.error(f"Could not load company for CIN: {st.session_state.selected_cin}")


if __name__ == '__main__':
    main()