import io
import json
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
import pandas as pd
import pycountry
import requests
import streamlit as st
from google.oauth2.service_account import Credentials
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

st.set_page_config(page_title="SuperDashboard", page_icon="🎫", layout="wide")
TZ = ZoneInfo("Asia/Jakarta")
ROLES = {
    "sales.support@meritz-korindo.co.id": "Sales Support",
    "zakiatulmuna@korindo.co.id": "Marketing",
    "gilang.k@korindo.co.id": "Underwriting",
    "vandytiagladis@korindo.co.id": "Reinsurance",
    "henryimmanuel@korindo.co.id": "Admin",
}
SOURCES = ["Direct Business", "Inward Fac. Business", "Direct Client/Broker", "R/I Broker/Ceding Company"]
CLASSES = ["PAREQ", "MB"]  # Add more classes here
CURRENCIES = ["IDR", "USD", "EUR", "SGD", "JPY", "AUD", "GBP", "CNY"]
FINAL_STATUSES = ["Accept", "Confirm", "Binding", "Booked", "Decline"]
HEADERS = [
    "ticket_id", "status", "created_at", "created_by", "source_of_business", "marketing_name",
    "class_of_business", "period_from", "period_to", "insured_name", "occupation",
    "country", "province", "city", "risk_detail", "currency", "total_sum_insured",
    "brokerage_ric", "process_reinsurance", "marketing_information", "sales_confirmed_at",
    "marketing_reviewed_by", "marketing_reviewed_at", "reinsurance_information",
    "reinsurance_reviewed_by", "reinsurance_reviewed_at", "uw_status", "our_role", "our_share_pct",
    "underwriting_recommendation", "own_retention_pct", "qs_pct", "spl_pct", "facultative_pct",
    "allocation_total_pct", "uw_confirmed_by", "uw_confirmed_at", "updated_at", "updated_by"
]
AUDIT_HEADERS = ["timestamp", "ticket_id", "action", "username", "from_status", "to_status", "details"]


CUSTOM_CSS = """
<style>
:root { --ink:#14273f; --muted:#66788e; --line:#e5ebf2; --accent:#1557a0; }
.block-container { max-width: 1460px; padding-top: 1.35rem; padding-bottom: 2rem; }
h1 { font-size: 1.7rem !important; letter-spacing: -.035em; font-weight: 730 !important; color:var(--ink) !important; }
h2, h3 { letter-spacing: -.015em; color: var(--ink) !important; }
h3 { font-size:1.1rem !important; margin-top:.35rem !important; }
[data-testid="stSidebar"] { background: #10263f; }
[data-testid="stSidebar"] * { color:#eef4fc !important; }
[data-testid="stSidebar"] button { background:#1a3859 !important; border-color:#385675 !important; }
[data-testid="stMetric"] { border:1px solid var(--line); background: #fff; padding: 13px 17px; border-radius: 12px; box-shadow:0 2px 10px rgba(19,46,82,.035); }
[data-testid="stMetricLabel"] { color:var(--muted); }
[data-testid="stMetricValue"] { color:var(--ink); font-size:1.65rem; }
[data-testid="stForm"] { padding: 1.15rem 1.2rem; border:1px solid var(--line); border-radius:12px; background: #fff; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:10px; overflow:hidden; }
[data-testid="stTabs"] button { font-weight:600; }
.stButton>button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] { background:#1557a0; border-color:#1557a0; }
[data-testid="stVerticalBlock"] { gap:.66rem; }
[data-testid="stCaptionContainer"] { color:var(--muted); }
.actuarial-card { border:1px solid #dce5f0; background:linear-gradient(120deg,#f6f9fe,#fff); padding:13px 17px; border-radius:12px; margin:2px 0 12px; }
.actuarial-label { font-size:11px; font-weight:750; letter-spacing:.09em; color:#536982; }
.actuarial-value { font-size:25px; font-weight:700; margin-top:3px; color:#1c436c; }
.actuarial-note { font-size:11px; color:#7c8b9b; margin-top:3px; }
.tagline { font-size:13px; font-weight:750; letter-spacing:.07em; color:#1f639e; margin:-5px 0 12px; }
</style>
"""


def apply_theme():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def actuarial_insight():
    """Display-only placeholders; no numbers are calculated yet."""
    st.markdown("#### Actuarial Insight")
    left, right = st.columns(2)
    with left:
        st.markdown("<div class='actuarial-card'><div class='actuarial-label'>LOSS RATIO</div><div class='actuarial-value'>—</div><div class='actuarial-note'>Awaiting actuarial data</div></div>", unsafe_allow_html=True)
    with right:
        st.markdown("<div class='actuarial-card'><div class='actuarial-label'>COMBINED RATIO</div><div class='actuarial-value'>—</div><div class='actuarial-note'>Awaiting actuarial data</div></div>", unsafe_allow_html=True)


def now():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S WIB")


@st.cache_resource(show_spinner=False)
def get_spreadsheet():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp"]), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(st.secrets["spreadsheet_id"])


def get_worksheet(title, headers):
    spreadsheet = get_spreadsheet()
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(30, len(headers)))
    existing = ws.row_values(1)
    if not existing:
        ws.update(range_name="A1", values=[headers])
    elif existing != headers:
        raise ValueError(f"Header tab {title} tidak cocok. Jangan mengubah urutan header yang dibuat aplikasi.")
    return ws


def ticket_ws():
    return get_worksheet("Tickets", HEADERS)


def audit_ws():
    return get_worksheet("AuditLog", AUDIT_HEADERS)


@st.cache_data(ttl=45, show_spinner=False)
def load_tickets():
    ws = ticket_ws()
    vals = ws.get_all_values()
    if len(vals) <= 1:
        return []
    out = []
    for row_num, values in enumerate(vals[1:], start=2):
        if not any(values):
            continue
        d = {key: (values[i] if i < len(values) else "") for i, key in enumerate(HEADERS)}
        d["_row"] = row_num
        out.append(d)
    return out


def invalidate_tickets():
    load_tickets.clear()


def log_action(ticket_id, action, user, old, new, details=""):
    audit_ws().append_row([now(), str(ticket_id), action, user, old, new, details], value_input_option="RAW")


def append_ticket(d):
    # A small-app MVP: max+1 is not atomic across simultaneous requests.
    values = [str(d.get(h, "")) for h in HEADERS]
    ticket_ws().append_row(values, value_input_option="RAW")
    invalidate_tickets()


def update_ticket(d):
    row = int(d["_row"])
    ticket_ws().update(range_name=f"A{row}:AM{row}", values=[[str(d.get(h, "")) for h in HEADERS]], value_input_option="RAW")
    invalidate_tickets()


def open_ticket(ticket_id):
    st.session_state.selected_ticket = str(ticket_id)
    st.rerun()


def page_back():
    st.session_state.selected_ticket = None
    st.rerun()


def show_table(rows, key, empty_message="Belum ada tiket."):
    """Client-side search/pagination; render only current page and defer PDFs until opened."""
    if not rows:
        st.info(empty_message)
        return
    search_col, page_size_col = st.columns([4, 1.2], vertical_alignment="bottom")
    with search_col:
        query = st.text_input(
            "Search ticket / insured name", key=f"{key}_search",
            placeholder="Cari nomor tiket atau insured name...",
            label_visibility="collapsed",
        ).strip().casefold()
    with page_size_col:
        page_size = st.selectbox("Rows", [10, 20, 50], index=0, key=f"{key}_size", label_visibility="collapsed")
    filtered = [x for x in rows if not query or query in str(x['ticket_id']).casefold() or query in str(x['insured_name']).casefold()]
    filtered.sort(key=lambda x: int(x['ticket_id']) if str(x['ticket_id']).isdigit() else 0, reverse=True)
    n = len(filtered)
    total_pages = max(1, (n + page_size - 1) // page_size)
    page_key = f"{key}_page"
    filter_key = f"{key}_filter_signature"
    signature = (query, page_size)
    if st.session_state.get(filter_key) != signature:
        st.session_state[page_key] = 1
        st.session_state[filter_key] = signature
    current_page = min(max(1, int(st.session_state.get(page_key, 1))), total_pages)
    st.session_state[page_key] = current_page
    left = (current_page - 1) * page_size
    page_rows = filtered[left:left + page_size]
    if not page_rows:
        st.info("Tidak ada tiket yang cocok dengan pencarian.")
        return
    # Only current page is rendered; no duplicate full-length list of buttons.
    data = pd.DataFrame([{
        "Ticket #": f"#{x['ticket_id']}",
        "Insured Name": x['insured_name'] or "—",
        "Class": x['class_of_business'] or "—",
        "Status": x['status'],
        "Last Update": x['updated_at'],
    } for x in page_rows])
    st.dataframe(data, hide_index=True, use_container_width=True, height=min(39 + len(page_rows) * 35, 435))
    st.caption("Pilih nomor tiket untuk melihat detail dan PDF. PDF hanya dibuat saat tiket dibuka.")
    with st.container():
        cols = st.columns(5)
        for i, rec in enumerate(page_rows):
            with cols[i % 5]:
                if st.button(f"#{rec['ticket_id']}", key=f"{key}_open_{rec['ticket_id']}", use_container_width=True):
                    open_ticket(rec['ticket_id'])
    nav1, nav2, nav3, nav4 = st.columns([2, 1, 1, 2], vertical_alignment="center")
    nav1.caption(f"Menampilkan {left + 1}–{left + len(page_rows)} dari {n} tiket")
    with nav2:
        if st.button("← Prev", key=f"{key}_prev", disabled=current_page <= 1, use_container_width=True):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with nav3:
        if st.button("Next →", key=f"{key}_next", disabled=current_page >= total_pages, use_container_width=True):
            st.session_state[page_key] = current_page + 1
            st.rerun()
    nav4.caption(f"Page {current_page} / {total_pages}")


def safe(x):
    return html.escape(str(x or "—")).replace("\n", "<br/>")


def pdf_bytes(d):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=37, leftMargin=37, topMargin=37, bottomMargin=37)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DashboardTitle", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=17, spaceAfter=12))
    styles.add(ParagraphStyle(name="DashboardBody", parent=styles["BodyText"], fontSize=9, leading=13))
    styles.add(ParagraphStyle(name="DashboardSmall", parent=styles["BodyText"], fontSize=8, leading=11, textColor=colors.HexColor("#555555")))
    story = [Paragraph("SUPERDASHBOARD — ACCEPTANCE TICKET", styles["DashboardTitle"]),
             Paragraph("#BePaperless", styles["DashboardSmall"]), Spacer(1, 6),
             Paragraph(f"Ticket #{safe(d['ticket_id'])} | Status: {safe(d['status'])}", styles["Heading2"]), Spacer(1, 9)]
    def section(title, pairs):
        story.append(Paragraph(safe(title), styles["Heading3"]))
        data = [[Paragraph(safe(label), styles["DashboardBody"]), Paragraph(safe(value), styles["DashboardBody"])] for label, value in pairs]
        tbl = Table(data, colWidths=[145, 367], hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F5F8")),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 10))
    section("Sales Support / Quotation", [
        ("Source of Business", d["source_of_business"]), ("Marketing Name", d["marketing_name"]),
        ("Class of Business", d["class_of_business"]),
        ("Period of Insurance", f"{d['period_from']} to {d['period_to']}"),
        ("Insured Name", d["insured_name"]), ("Occupation", d["occupation"]),
        ("Risk Location", ", ".join(str(d[k]) for k in ["risk_detail", "city", "province", "country"] if d[k])),
        ("Total Sum Insured", f"{d['currency']} {d['total_sum_insured']}"),
        ("Brokerage / RIC", f"{d['currency']} {d['brokerage_ric']}"),
        ("Process to Reinsurance", "Yes" if d["process_reinsurance"] == "Yes" else "No"),
    ])
    section("Actuarial Insight", [
        ("Loss Ratio", "Pending actuarial data"),
        ("Combined Ratio", "Pending actuarial data"),
    ])
    section("Marketing Information", [
        ("Marketing Information", d["marketing_information"]),
        ("Filled by", f"{d['created_by']} at {d['sales_confirmed_at']}")
    ])
    section("Marketing Review", [
        ("Reviewed by Marketing", f"{d['marketing_reviewed_by']} at {d['marketing_reviewed_at']}" if d["marketing_reviewed_at"] else "Pending")
    ])
    if d["process_reinsurance"] == "Yes":
        section("Reinsurance", [
            ("Reinsurance Information", d["reinsurance_information"]),
            ("Reviewed by Reinsurance", f"{d['reinsurance_reviewed_by']} at {d['reinsurance_reviewed_at']}" if d["reinsurance_reviewed_at"] else "Pending")
        ])
    section("Underwriting", [
        ("Final Decision", d["uw_status"]), ("Our Role", d["our_role"]),
        ("Our Share (%)", d["our_share_pct"]), ("Underwriting Recommendation", d["underwriting_recommendation"]),
        ("Own Retention (%)", d["own_retention_pct"]), ("Treaty QS (%)", d["qs_pct"]),
        ("Treaty SPL (%)", d["spl_pct"]), ("Facultative (%)", d["facultative_pct"]),
        ("Allocation Total (%)", d["allocation_total_pct"]),
        ("Confirmed by", f"{d['uw_confirmed_by']} at {d['uw_confirmed_at']}" if d["uw_confirmed_at"] else "Pending")
    ])
    story.append(Paragraph(f"Generated at {now()} | Internal workflow record — not an insurance policy or binder.", styles["DashboardSmall"]))
    doc.build(story)
    return buffer.getvalue()


@st.cache_data(ttl=86400, show_spinner=False)
def provinces():
    try:
        r = requests.get("https://www.emsifa.com/api-wilayah-indonesia/api/provinces.json", timeout=7)
        r.raise_for_status()
        return {x["name"]: x["id"] for x in r.json()}
    except Exception:
        return {"DKI JAKARTA": "31", "JAWA BARAT": "32", "BANTEN": "36", "JAWA TENGAH": "33", "JAWA TIMUR": "35", "BALI": "51"}


@st.cache_data(ttl=86400, show_spinner=False)
def cities(province_id):
    try:
        r = requests.get(f"https://www.emsifa.com/api-wilayah-indonesia/api/regencies/{province_id}.json", timeout=7)
        r.raise_for_status()
        return sorted(x["name"] for x in r.json())
    except Exception:
        return []


def new_ticket(user):
    st.subheader("Create New Acceptance Ticket")
    st.caption("Complete quotation details • Fields marked * are mandatory")
    # Dynamic locations outside form: changes update dependent city selector immediately.
    lcol, rcol = st.columns(2, gap="large")
    with lcol:
        src = st.selectbox("Source of Business *", SOURCES)
        marketing_name = st.text_input("Marketing Name *") if src in SOURCES[2:] else ""
    with rcol:
        country_names = sorted({c.name for c in pycountry.countries})
        country = st.selectbox("Country *", country_names, index=country_names.index("Indonesia"))
    if country == "Indonesia":
        provs = provinces()
        names = list(provs)
        default_prov = next((n for n in names if "JAKARTA" in n.upper()), names[0])
        location_l, location_r = st.columns(2, gap="large")
        with location_l:
            province = st.selectbox("Province *", names, index=names.index(default_prov))
        city_choices = cities(provs[province])
        with location_r:
            city = st.selectbox("City *", city_choices) if city_choices else st.text_input("City *")
    else:
        location_l, location_r = st.columns(2, gap="large")
        with location_l:
            province = st.text_input("Province / State *")
        with location_r:
            city = st.text_input("City *")
    with st.form("new_ticket", clear_on_submit=False):
        st.markdown("#### Business & Policy Details")
        c1, c2 = st.columns(2, gap="large")
        with c1:
            class_of_business = st.selectbox("Class of Business *", CLASSES)
            insured = st.text_input("Insured Name *")
            period_from = st.date_input("Period of Insurance — From *")
            currency = st.selectbox("Currency", CURRENCIES)
            sum_insured = st.number_input("Total Sum Insured *", min_value=0.0, step=1000000.0, format="%.2f")
        with c2:
            occupation = st.text_input("Occupation *")
            detail = st.text_input("Risk Location — Detail *")
            period_to = st.date_input("Period of Insurance — Up to *")
            brokerage = st.number_input("Brokerage / RIC", min_value=0.0, step=100000.0, format="%.2f")
            to_reins = st.checkbox("Proses Tiket ke Reasuransi")
        actuarial_insight()
        st.markdown("#### Marketing Information")
        marketing_info = st.text_area("Information & Explanation *", height=125, label_visibility="collapsed", placeholder="Provide marketing background, client context and quotation notes...")
        declaration = st.checkbox("Saya menyatakan bahwa informasi yang saya isi sudah benar")
        submit = st.form_submit_button("Process Ticket →", type="primary", use_container_width=True)
    if submit:
        errors = []
        if src in SOURCES[2:] and not marketing_name.strip():
            errors.append("Marketing Name wajib diisi untuk source yang dipilih.")
        if period_to < period_from:
            errors.append("Tanggal Up to harus sama atau sesudah From.")
        if not insured.strip() or not occupation.strip() or not detail.strip() or not marketing_info.strip() or not province.strip() or not city.strip():
            errors.append("Insured, Occupation, Province, City, Risk Detail, dan Marketing Information wajib diisi.")
        if sum_insured <= 0:
            errors.append("Total Sum Insured harus lebih dari nol.")
        if not declaration:
            errors.append("Harap centang pernyataan kebenaran data.")
        if errors:
            for error in errors:
                st.error(error)
            return
        tickets = load_tickets()
        tid = str(max((int(t["ticket_id"]) for t in tickets), default=0) + 1)
        stamp = now()
        d = {h: "" for h in HEADERS}
        d.update({
            "ticket_id": tid, "status": "Pending Marketing", "created_at": stamp,
            "created_by": user, "source_of_business": src, "marketing_name": marketing_name,
            "class_of_business": class_of_business, "period_from": str(period_from), "period_to": str(period_to),
            "insured_name": insured, "occupation": occupation,
            "country": country, "province": province,
            "city": city, "risk_detail": detail,
            "currency": currency, "total_sum_insured": f"{sum_insured:.2f}",
            "brokerage_ric": f"{brokerage:.2f}", "process_reinsurance": "Yes" if to_reins else "No",
            "marketing_information": marketing_info, "sales_confirmed_at": stamp,
            "updated_at": stamp, "updated_by": user
        })
        append_ticket(d)
        log_action(tid, "CREATE", user, "", "Pending Marketing", "Ticket created by Sales Support")
        st.success(f"Ticket #{tid} berhasil dibuat. Status: Pending Marketing")
        st.session_state.selected_ticket = tid
        st.rerun()


def detail_ticket(d, role, user):
    st.button("← Back to Dashboard", on_click=page_back)
    st.subheader(f"Ticket #{d['ticket_id']} — {d['insured_name']}")
    st.caption("SuperDashboard  ·  #BePaperless")
    st.info(f"Current Status: {d['status']}")
    actuarial_insight()
    if st.toggle("Show PDF preview / download", value=False, key=f"pdf_{d['ticket_id']}"):
        pdf = pdf_bytes(d)
        st.download_button("⬇ Download Ticket PDF", pdf, file_name=f"SuperDashboard_Ticket_{d['ticket_id']}.pdf", mime="application/pdf")
        st.pdf(pdf, height=560)
    else:
        st.caption("PDF loaded on demand to keep this page fast. Enable the preview above to view or download.")
    if role == "Admin":
        st.caption("Admin: read-only overview (no approval overrides in this MVP).")
        return
    if role == "Marketing" and d["status"] == "Pending Marketing":
        st.divider()
        st.subheader("Marketing Review")
        with st.form("marketing_form"):
            info = st.text_area("Marketing Information (editable)", value=d["marketing_information"], height=180)
            submit = st.form_submit_button("Confirm & Proceed", type="primary")
        if submit:
            if not info.strip():
                st.error("Marketing Information wajib diisi.")
                return
            current = next((x for x in load_tickets() if x["ticket_id"] == d["ticket_id"]), None)
            if not current or current["status"] != "Pending Marketing":
                st.error("Status sudah berubah. Refresh halaman.")
                return
            next_status = "Pending Reinsurance" if current["process_reinsurance"] == "Yes" else "Pending UW"
            current.update({"marketing_information": info, "marketing_reviewed_by": user, "marketing_reviewed_at": now(),
                            "status": next_status, "updated_at": now(), "updated_by": user})
            update_ticket(current)
            log_action(d["ticket_id"], "MARKETING_APPROVE", user, "Pending Marketing", next_status)
            st.success(f"Diteruskan ke {next_status}")
            st.rerun()
    elif role == "Reinsurance" and d["status"] == "Pending Reinsurance":
        st.divider()
        st.subheader("Reinsurance Review")
        with st.form("reins_form"):
            info = st.text_area("Reinsurance Information *", value=d["reinsurance_information"], height=200)
            submit = st.form_submit_button("Proceed to Underwriters", type="primary")
        if submit:
            if not info.strip():
                st.error("Reinsurance Information wajib diisi.")
                return
            current = next((x for x in load_tickets() if x["ticket_id"] == d["ticket_id"]), None)
            if not current or current["status"] != "Pending Reinsurance":
                st.error("Status sudah berubah. Refresh halaman.")
                return
            current.update({"reinsurance_information": info, "reinsurance_reviewed_by": user,
                            "reinsurance_reviewed_at": now(), "status": "Pending UW", "updated_at": now(), "updated_by": user})
            update_ticket(current)
            log_action(d["ticket_id"], "REINSURANCE_PROCEED", user, "Pending Reinsurance", "Pending UW")
            st.success("Diteruskan ke Underwriting")
            st.rerun()
    elif role == "Underwriting" and d["status"] == "Pending UW":
        st.divider()
        st.subheader("Underwriting Decision & Allocation")
        with st.form("uw_form"):
            ua, ub, uc = st.columns(3)
            with ua:
                decision = st.selectbox("Final Status *", FINAL_STATUSES)
            with ub:
                share_role = st.selectbox("Our Role", ["Leader", "Member"])
            with uc:
                our_share = st.number_input("Our Share (%)", min_value=0.0, max_value=100.0, value=100.0, step=0.01)
            recommendation = st.text_area("Underwriting Recommendation *", height=125)
            st.markdown("**Risk Allocation (% of Our Share)**")
            c1, c2 = st.columns(2)
            with c1:
                own = st.number_input("Own Retention (%)", min_value=0.0, max_value=100.0, value=100.0, step=0.01)
                qs = st.number_input("Treaty — QS (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.01)
            with c2:
                spl = st.number_input("Treaty — SPL (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.01)
                fac = st.number_input("Facultative (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.01)
            total = own + qs + spl + fac
            st.metric("Total Risk Allocation", f"{total:.2f}%")
            submit = st.form_submit_button("Confirm Underwriting", type="primary", use_container_width=True)
        if submit:
            if abs(total - 100.0) > 0.001:
                st.error(f"Risk Allocation harus tepat 100%. Sekarang {total:.2f}%")
                return
            if not recommendation.strip():
                st.error("Underwriting Recommendation wajib diisi.")
                return
            current = next((x for x in load_tickets() if x["ticket_id"] == d["ticket_id"]), None)
            if not current or current["status"] != "Pending UW":
                st.error("Status sudah berubah. Refresh halaman.")
                return
            current.update({
                "uw_status": decision, "status": decision, "our_role": share_role,
                "our_share_pct": f"{our_share:.2f}", "underwriting_recommendation": recommendation,
                "own_retention_pct": f"{own:.2f}", "qs_pct": f"{qs:.2f}", "spl_pct": f"{spl:.2f}",
                "facultative_pct": f"{fac:.2f}", "allocation_total_pct": f"{total:.2f}",
                "uw_confirmed_by": user, "uw_confirmed_at": now(), "updated_at": now(), "updated_by": user
            })
            update_ticket(current)
            log_action(d["ticket_id"], "UW_FINAL", user, "Pending UW", decision, f"Allocation {total:.2f}%")
            st.success(f"Tiket selesai: {decision}")
            st.rerun()
    else:
        st.caption("Tidak ada tindakan yang tersedia untuk akun ini pada status saat ini.")


def login():
    st.title("🎫 SuperDashboard")
    st.markdown('<div class="tagline">#BePaperless</div>', unsafe_allow_html=True)
    st.write("Quotation Acceptance & Ticket Workflow")
    st.caption("Internal application — authorized personnel only")
    with st.form("login_form"):
        email = st.text_input("Username / Email").strip().lower()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary")
    if submitted:
        configured_users = dict(st.secrets.get("users", {}))
        if email in ROLES and email in configured_users and password == str(configured_users[email]):
            st.session_state.user = email
            st.session_state.selected_ticket = None
            st.rerun()
        else:
            st.error("Username atau password salah.")
    st.warning("Prototype login: gunakan hanya untuk pengujian internal. Untuk produksi, gunakan company SSO/MFA dan role-based identity.")


def main():
    apply_theme()
    if "user" not in st.session_state:
        login()
        return
    user = st.session_state.user
    role = ROLES[user]
    st.sidebar.title("🎫 SuperDashboard")
    st.sidebar.caption("#BePaperless")
    st.sidebar.write(f"**{role}**")
    st.sidebar.caption(user)
    if st.sidebar.button("Log out"):
        del st.session_state.user
        st.session_state.selected_ticket = None
        st.rerun()
    try:
        all_tickets = load_tickets()
        audit_ws()  # ensure audit tab exists
    except Exception as e:
        st.error("Google Sheets connection error. Check spreadsheet_id, Service Account sharing, Secrets, and Sheets API.")
        st.code(f"{type(e).__name__}: {e}")
        st.stop()

    selected = st.session_state.get("selected_ticket")
    if selected:
        record = next((t for t in all_tickets if t["ticket_id"] == selected), None)
        if not record:
            st.error("Ticket tidak ditemukan.")
            page_back()
        if role == "Reinsurance" and record["process_reinsurance"] != "Yes":
            st.error("Akses tidak diizinkan.")
            page_back()
        if role == "Sales Support" and record["created_by"] != user:
            st.error("Akses tidak diizinkan.")
            page_back()
        if role == "Underwriting" and record["status"] not in (["Pending UW"] + FINAL_STATUSES):
            st.error("Tiket belum sampai tahap Underwriting.")
            page_back()
        if role == "Reinsurance" and record["marketing_reviewed_at"] == "":
            st.error("Tiket belum sampai tahap Reinsurance.")
            page_back()
        detail_ticket(record, role, user)
        return

    st.title("SuperDashboard")
    st.markdown('<div class="tagline">#BePaperless</div>', unsafe_allow_html=True)
    st.caption(f"Logged in: {user} · {role} · Asia/Jakarta timezone")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Tickets", len(all_tickets))
    c2.metric("Pending", sum(x["status"].startswith("Pending") for x in all_tickets))
    c3.metric("Completed", sum(x["status"] in FINAL_STATUSES for x in all_tickets))

    if role == "Sales Support":
        tabs = st.tabs(["My Tickets", "➕ New Ticket"])
        with tabs[0]:
            st.subheader("My Submitted Tickets")
            show_table([x for x in all_tickets if x["created_by"] == user], "sales")
        with tabs[1]:
            new_ticket(user)
    elif role == "Marketing":
        st.subheader("1. Pending Marketing")
        show_table([x for x in all_tickets if x["status"] == "Pending Marketing"], "marketing_pending")
        st.subheader("2. Reviewed Tickets / Progress")
        show_table([x for x in all_tickets if x["marketing_reviewed_at"]], "marketing_done")
    elif role == "Reinsurance":
        st.subheader("1. Pending Reinsurance")
        show_table([x for x in all_tickets if x["status"] == "Pending Reinsurance"], "reins_pending")
        st.subheader("2. Processed Reinsurance Tickets")
        show_table([x for x in all_tickets if x["process_reinsurance"] == "Yes" and x["reinsurance_reviewed_at"]], "reins_done")
    elif role == "Underwriting":
        st.subheader("1. Pending Underwriting")
        show_table([x for x in all_tickets if x["status"] == "Pending UW"], "uw_pending")
        st.subheader("2. Finished Tickets")
        show_table([x for x in all_tickets if x["status"] in FINAL_STATUSES], "uw_done")
    else:
        st.subheader("All Tickets — Admin Overview")
        show_table(all_tickets, "admin_all")
        st.subheader("Status Summary")
        if all_tickets:
            counts = pd.Series([x["status"] for x in all_tickets]).value_counts()
            st.bar_chart(counts)
        st.info("Full audit trail is stored in the AuditLog worksheet in Google Sheets.")
    if st.button("🔄 Refresh Data"):
        invalidate_tickets()
        st.rerun()


if __name__ == "__main__":
    main()
