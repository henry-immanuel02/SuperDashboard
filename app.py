import io
from urllib.parse import urlparse
import base64
import hashlib
import math
import mimetypes
import json
import html
import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
import pandas as pd
import pycountry
import requests
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable

st.set_page_config(page_title="SuperDashboard", page_icon="🎫", layout="wide")
TZ = ZoneInfo("Asia/Jakarta")
ROLES = {
    "sales.support@meritz-korindo.co.id": "Sales Support",
    "zakiatulmuna@korindo.co.id": "Marketing",
    "gilang.k@korindo.co.id": "Underwriting",
    "vandytiagladis@korindo.co.id": "Reinsurance",
    "henryimmanuel@korindo.co.id": "Admin",
    "hadi@korindo.co.id": "Technical Director",
    "jhson@korindo.co.id": "Marketing Director",
    "sweetchj@korindo.co.id": "President Director",
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
EXTRA_HEADERS = [
    "our_client", "additional_form", "additional_date", "additional_ps_no",
    "additional_intermediary", "additional_insured", "additional_coverage",
    "additional_fee", "additional_status", "additional_sales_signed_by",
    "additional_sales_signed_at", "additional_marketing_signed_by",
    "additional_marketing_signed_at", "additional_technical_signed_by",
    "additional_technical_signed_at", "additional_marketing_director_signed_by",
    "additional_marketing_director_signed_at", "additional_president_signed_by",
    "additional_president_signed_at",
]
HEADERS += EXTRA_HEADERS
# Append-only schema migration: preserve existing ticket rows and column order.
HEADERS += ["exchange_rate_idr", "sum_insured_idr", "premium_rate_pct", "premium_original", "premium_idr"]
# New fields always appended to preserve existing Google Sheets data.
HEADERS += ["renewal_business"]
CHAT_HEADERS = ["timestamp", "ticket_id", "username", "role", "type", "target_role", "message"]
MENTION_HEADERS = ["mention_id", "timestamp", "ticket_id", "sender", "recipient", "message_excerpt"]
MENTION_READ_HEADERS = ["mention_id", "username", "read_at"]
AUDIT_HEADERS = ["timestamp", "ticket_id", "action", "username", "from_status", "to_status", "details"]
ATTACHMENT_HEADERS = [
    "attachment_id", "ticket_id", "category", "filename", "mime_type",
    "size_bytes", "chunk_index", "chunk_count", "payload_base64",
    "uploaded_by", "uploaded_at", "sha256"
]
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "zip"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MiB per file
MAX_FILES_PER_SUBMISSION = 8
MAX_TOTAL_BYTES = 10 * 1024 * 1024  # Maximum combined size per ticket
CHUNK_CHARS = 30000  # Compatibility with legacy small attachments



CUSTOM_CSS = """
<style>
:root { --ink:#14273f; --muted:#66788e; --line:#e5ebf2; --accent:#1557a0; }
.block-container { max-width: 1480px; padding-top: 5.4rem !important; padding-bottom: 2.5rem; }
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
[data-testid="stDataFrame"] { border:1px solid #dce5f0; border-radius:14px; overflow:hidden; box-shadow:0 7px 24px rgba(20,46,79,.055); }
[data-testid="stDataFrame"] [role="columnheader"] { background:#edf3fa !important; color:#193956 !important; font-weight:700 !important; }
[data-testid="stDataFrame"] [role="row"] { cursor:pointer; }
[data-testid="stDataFrame"] [role="row"]:hover { background:#edf5ff !important; }
[data-testid="stDataFrame"] [aria-selected="true"] { background:#dcecff !important; }
[data-testid="stDataFrame"] [data-testid="stElementToolbar"] { display:none; }
[data-testid="stDownloadButton"] button { background:#1463bf !important; border:1px solid #1463bf !important; color:#fff !important; font-weight:650 !important; border-radius:9px !important; }
[data-testid="stDownloadButton"] button:hover { background:#0f4e99 !important; border-color:#0f4e99 !important; color:white !important; }
.st-key-ticket_preview { border:1px solid var(--line); border-radius:12px; }

[data-testid="stTabs"] button { font-weight:600; }
.stButton>button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] { background:#1557a0; border-color:#1557a0; }
[data-testid="stVerticalBlock"] { gap:.66rem; }
[data-testid="stCaptionContainer"] { color:var(--muted); }
.actuarial-card { border:1px solid #dce5f0; background:linear-gradient(120deg,#f6f9fe,#fff); padding:13px 17px; border-radius:12px; margin:2px 0 12px; }
.actuarial-label { font-size:11px; font-weight:750; letter-spacing:.09em; color:#536982; }
.actuarial-value { font-size:25px; font-weight:700; margin-top:3px; color:#1c436c; }
.actuarial-note { font-size:11px; color:#7c8b9b; margin-top:3px; }
.notification-heading {font-size:15px;font-weight:750;color:#193956;margin:12px 0 8px;}
.notification-heading span {font-size:12px;color:#a44a16;font-weight:650;margin-left:8px;}
.signature-card { border:1px solid #dce5ef; border-radius:10px; padding:12px 14px; min-height:94px; background:#fff; }
.signature-role {font-size:11px;font-weight:750;color:#60768c;text-transform:uppercase;letter-spacing:.045em;}
.signature-value {margin-top:10px;font-size:12px;color:#1d426a;font-weight:600;}
.signature-value span {font-size:10px;color:#6b7d8f;font-weight:400;}
.tagline { font-size:13px; font-weight:750; letter-spacing:.07em; color:#1f639e; margin:-5px 0 12px; }
[data-testid="stAppViewContainer"] { background:#f8fafc; }
[data-testid="stHeader"] { background:transparent; }
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


def column_letter(n):
    result = ""
    while n:
        n, rem = divmod(n-1, 26)
        result = chr(65+rem) + result
    return result


def get_worksheet(title, headers):
    spreadsheet = get_spreadsheet()
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(30, len(headers)))
    existing = ws.row_values(1)
    if title == "Tickets" and existing and existing != headers and headers[:len(existing)] == existing:
        # Non-destructive migration: append new columns to the right of existing data.
        if ws.col_count < len(headers):
            ws.add_cols(len(headers) - ws.col_count)
        ws.update(range_name=f"{column_letter(len(existing)+1)}1:{column_letter(len(headers))}1", values=[headers[len(existing):]])
        existing = headers
    if not existing:
        ws.update(range_name="A1", values=[headers])
    elif existing != headers:
        raise ValueError(f"Header tab {title} tidak cocok. Jangan mengubah urutan header yang dibuat aplikasi.")
    return ws


def attachment_ws():
    return get_worksheet("TicketAttachments", ATTACHMENT_HEADERS)


def validate_uploads(renewal, previous, supporting, existing_bytes=0, existing_count=0):
    """Validate uploads before creating any ticket or writing any file."""
    errors = []
    previous = list(previous or [])
    supporting = list(supporting or [])
    files = [("Previous Document", f) for f in previous] + [("Supporting Document", f) for f in supporting]
    if previous and not renewal:
        errors.append("Previous Document hanya tersedia untuk Renewal Business.")
    if len(files) + existing_count > MAX_FILES_PER_SUBMISSION:
        errors.append(f"Maksimal {MAX_FILES_PER_SUBMISSION} dokumen per pengajuan.")
    total_bytes = 0
    for category, file in files:
        ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f"Format file tidak didukung: {file.name}.")
        total_bytes += file.size
        if file.size > MAX_FILE_BYTES:
            errors.append(f"{file.name} melebihi batas 10 MB per dokumen. Upload ke Google Drive, lalu masukkan linknya.")
        if file.size == 0:
            errors.append(f"{file.name} kosong.")
    if total_bytes + existing_bytes > MAX_TOTAL_BYTES:
        errors.append("Total dokumen melebihi 10 MB per tiket. Upload dokumen ke Google Drive, lalu masukkan linknya.")
    return errors, files


@st.cache_resource(show_spinner=False)
def drive_service():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp"]),
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_drive_folder_id():
    return str(st.secrets.get("drive_folder_id", "")).strip()


def drive_folder_ready():
    return bool(get_drive_folder_id())


def save_attachment(ticket_id, category, uploaded_file, user):
    """Save new binary files in a Google Shared Drive folder; keep Sheets metadata.

    Existing Sheets/base64 attachments are still readable. The Shared Drive must
    have granted this service account permission to upload files.
    """
    if not drive_folder_ready():
        raise ValueError("Upload memerlukan drive_folder_id (folder Shared Drive) pada Streamlit Secrets. Atau unggah manual ke Google Drive dan masukkan link dokumen.")
    payload = uploaded_file.getvalue()
    if not 0 < len(payload) <= MAX_FILE_BYTES:
        raise ValueError("Ukuran file tidak valid atau melebihi 10 MB.")
    attachment_id = uuid.uuid4().hex
    digest = hashlib.sha256(payload).hexdigest()
    clean_name = uploaded_file.name.replace("/", "_").replace("\\", "_")[:180]
    mime = mimetypes.guess_type(clean_name)[0] or "application/octet-stream"
    timestamp = now()
    service = drive_service()
    request = service.files().create(
        body={"name": f"Ticket-{ticket_id}_{attachment_id[:8]}_{clean_name}",
              "parents": [get_drive_folder_id()], "description": f"SuperDashboard ticket {ticket_id}"},
        media_body=MediaIoBaseUpload(io.BytesIO(payload), mimetype=mime, resumable=True),
        fields="id", supportsAllDrives=True
    )
    result = request.execute()
    file_id = result["id"]
    try:
        attachment_ws().append_row([
            attachment_id, str(ticket_id), category, clean_name, mime,
            str(len(payload)), "0", "1", f"DRIVE:{file_id}",
            user, timestamp, digest
        ], value_input_option="RAW")
    except Exception:
        try:
            service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        except Exception:
            pass
        raise
    log_action(ticket_id, "ATTACHMENT_UPLOAD", user, "", "", f"{category}: {clean_name} ({len(payload)} bytes)")
    load_attachment_manifest.clear()
    return attachment_id


LINK_HEADERS = ["link_id", "ticket_id", "category", "label", "url", "uploaded_by", "uploaded_at"]


def attachment_links_ws():
    return get_worksheet("TicketAttachmentLinks", LINK_HEADERS)


def valid_drive_link(url):
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme == "https" and parsed.hostname in ("drive.google.com", "docs.google.com")
    except Exception:
        return False


def save_attachment_link(ticket_id, category, label, url, user):
    if not valid_drive_link(url):
        raise ValueError("Masukkan URL Google Drive atau Google Docs yang valid (https://...).")
    label = label.strip()[:180] or "Google Drive document"
    attachment_links_ws().append_row(
        [uuid.uuid4().hex, str(ticket_id), category, label, url.strip(), user, now()],
        value_input_option="RAW"
    )
    log_action(ticket_id, "ATTACHMENT_LINK", user, "", "", f"{category}: {label}")
    load_attachment_links.clear()


@st.cache_data(ttl=30, show_spinner=False)
def load_attachment_links(ticket_id):
    rows = attachment_links_ws().get_all_records()
    return [r for r in rows if str(r.get("ticket_id", "")) == str(ticket_id)]


def upload_limit_note():
    st.caption("PDF, Word, Excel, gambar, ZIP · Maksimal 10 MB per file dan 10 MB total per tiket · Maksimal 8 file.")
    st.info("Jika total lebih dari 10 MB, upload dokumen ke Google Drive lalu masukkan link dokumen. Pastikan penerima diberi akses Drive.")

@st.cache_data(ttl=30, show_spinner=False)
def load_attachment_manifest(ticket_id):
    """Only read lightweight metadata columns, never base64 until download."""
    ws = attachment_ws()
    # Avoid repeatedly loading the large binary payload column I.
    ids = ws.get("A2:H")
    info = ws.get("J2:L")
    records = {}
    for offset, meta in enumerate(ids):
        if len(meta) < 8 or str(meta[1]) != str(ticket_id):
            continue
        uid = meta[0]
        if uid not in records:
            extra = info[offset] if offset < len(info) else []
            records[uid] = {
                "attachment_id": uid, "category": meta[2], "filename": meta[3],
                "mime": meta[4], "size_bytes": int(meta[5]),
                "chunk_count": int(meta[7]), "rows": [],
                "uploaded_by": extra[0] if len(extra)>0 else "",
                "uploaded_at": extra[1] if len(extra)>1 else "",
                "sha256": extra[2] if len(extra)>2 else "",
            }
        records[uid]["rows"].append((int(meta[6]), offset + 2))
    return sorted(records.values(), key=lambda x: (x["uploaded_at"], x["filename"]), reverse=True)


def read_attachment(record):
    """Download legacy Sheets data or Drive binary only on explicit request."""
    ws = attachment_ws()
    ranges = [f"I{row}" for _, row in sorted(record["rows"])]
    parts = ws.batch_get(ranges)
    if len(parts) != record["chunk_count"]:
        raise ValueError("Jumlah bagian dokumen tidak lengkap.")
    first = parts[0][0][0] if parts and parts[0] and parts[0][0] else ""
    if first.startswith("DRIVE:"):
        file_id = first.split(":", 1)[1]
        request = drive_service().files().get_media(fileId=file_id, supportsAllDrives=True)
        stream = io.BytesIO()
        downloader = MediaIoBaseDownload(stream, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        payload = stream.getvalue()
    else:
        encoded = "".join(result[0][0] if result and result[0] else "" for result in parts)
        payload = base64.b64decode(encoded, validate=True)
    if len(payload) != record["size_bytes"] or hashlib.sha256(payload).hexdigest() != record["sha256"]:
        raise ValueError("Integritas dokumen gagal diverifikasi.")
    return payload


def attachment_panel(ticket_id, role, user, allow_upload=False, renewal_ticket=False):
    """List documents for authorized ticket viewers; owners may add files."""
    with st.expander("Documents & Attachments", expanded=False):
        records = load_attachment_manifest(ticket_id)
        links = load_attachment_links(ticket_id)
        if not records and not links:
            st.caption("Belum ada dokumen.")
        for record in records:
            c1, c2, c3 = st.columns([4, 2, 1.3], vertical_alignment="center")
            c1.markdown(f"**{html.escape(record['filename'])}**")
            c1.caption(f"{record['category']} · {record['size_bytes'] / 1024:.0f} KB")
            c2.caption(f"{record['uploaded_by']} · {record['uploaded_at']}")
            with c3:
                # A real button prevents fetching binary for closed ticket views.
                key = f"prepare_{record['attachment_id']}"
                if st.button("Open", key=key):
                    st.session_state[f"ready_{record['attachment_id']}"] = True
                if st.session_state.get(f"ready_{record['attachment_id']}"):
                    try:
                        payload = read_attachment(record)
                        st.download_button("Download", payload, file_name=record["filename"],
                                           mime=record["mime"], key=f"download_{record['attachment_id']}")
                    except Exception as exc:
                        st.error(f"Dokumen tidak dapat dibaca: {exc}")
        for link in links:
            st.markdown(f"**{html.escape(str(link['label']))}** · [Open in Google Drive]({link['url']})")
            st.caption(f"{link['category']} · {link['uploaded_by']} · {link['uploaded_at']}")
        if allow_upload:
            st.markdown("**Add Supporting Documents**")
            new_docs = st.file_uploader("Upload supporting documents", type=sorted(ALLOWED_EXTENSIONS),
                accept_multiple_files=True, key=f"more_files_{ticket_id}")
            new_previous = []
            if renewal_ticket:
                new_previous = st.file_uploader("Upload previous document", type=sorted(ALLOWED_EXTENSIONS),
                    accept_multiple_files=True, key=f"more_previous_{ticket_id}")
            upload_limit_note()
            if st.button("Upload Documents", key=f"upload_more_{ticket_id}", type="primary"):
                errs, files = validate_uploads(renewal_ticket, new_previous, new_docs,
                    existing_bytes=sum(r["size_bytes"] for r in records), existing_count=len(records))
                if files and not drive_folder_ready():
                    errs.append("Upload file memerlukan drive_folder_id pada Secrets. Gunakan Google Drive link di bawah jika belum tersedia.")
                if not new_docs and not new_previous:
                    errs.append("Pilih dokumen terlebih dahulu.")
                if errs:
                    for err in errs: st.error(err)
                else:
                    successes = 0
                    for category, doc in files:
                        try:
                            save_attachment(ticket_id, category, doc, user)
                            successes += 1
                        except Exception as exc:
                            st.error(f"Upload {doc.name} gagal: {exc}")
                    if successes:
                        st.success(f"{successes} dokumen tersimpan.")
                        st.rerun()
            st.markdown("**Google Drive Link**")
            with st.form(f"attachment_link_{ticket_id}"):
                link_cat = st.selectbox("Document category", ["Supporting Document"] + (["Previous Document"] if renewal_ticket else []))
                link_label = st.text_input("Document name")
                link_url = st.text_input("Google Drive URL", placeholder="https://drive.google.com/file/d/...")
                if st.form_submit_button("Save Link"):
                    try:
                        save_attachment_link(ticket_id, link_cat, link_label, link_url, user)
                        st.success("Link tersimpan.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


def ticket_ws():
    return get_worksheet("Tickets", HEADERS)


def audit_ws():
    return get_worksheet("AuditLog", AUDIT_HEADERS)


def chat_ws():
    return get_worksheet("TicketChat", CHAT_HEADERS)


@st.cache_data(ttl=15, show_spinner=False)
def load_chat(ticket_id):
    values = chat_ws().get_all_values()
    return [dict(zip(CHAT_HEADERS, row + [""] * (len(CHAT_HEADERS) - len(row))))
            for row in values[1:] if row and str(row[1]) == str(ticket_id)]


def mention_ws():
    return get_worksheet("TicketMentions", MENTION_HEADERS)


def mention_read_ws():
    return get_worksheet("MentionReads", MENTION_READ_HEADERS)


def mention_aliases(email):
    local = email.split("@")[0].lower()
    return {local, email.lower()}


def extract_mentions(message, selected_people, sender):
    people = set(selected_people)
    tokens = {t.lower().strip(".,:;!?()[]") for t in re.findall(r"@([\w.+-]+(?:@[\w.-]+)?)", message)}
    for email in ROLES:
        if tokens.intersection(mention_aliases(email)):
            people.add(email)
    people.discard(sender)
    return sorted(people)


@st.cache_data(ttl=20, show_spinner=False)
def load_mentions(username):
    # Separate small worksheets keep notifications independent of ticket schema.
    notices = mention_ws().get_all_values()[1:]
    read_ids = {row[0] for row in mention_read_ws().get_all_values()[1:]
                if len(row) >= 2 and row[1] == username}
    return [dict(zip(MENTION_HEADERS, row + [""] * (len(MENTION_HEADERS) - len(row))))
            for row in notices if len(row) >= 5 and row[4] == username and row[0] not in read_ids]


def mark_mentions_read(username, ids):
    if ids:
        timestamp = now()
        mention_read_ws().append_rows([[item, username, timestamp] for item in ids], value_input_option="RAW")
        load_mentions.clear()


def notification_panel(user, tickets):
    # Notifications display only mentions directed to the signed-in user.
    try:
        pending = load_mentions(user)
    except Exception:
        st.warning("Notifications are temporarily unavailable.")
        return
    if not pending:
        return
    pending.sort(key=lambda item: item["timestamp"], reverse=True)
    st.markdown(f'<div class="notification-heading">Mentions <span>{len(pending)} unread</span></div>', unsafe_allow_html=True)
    with st.container(border=True):
        display = pending[:50]
        data = pd.DataFrame([{
            "Ticket": f"#{item['ticket_id']}",
            "From": item["sender"].split("@")[0],
            "Message": item["message_excerpt"],
            "Time": item["timestamp"],
        } for item in display])
        event = st.dataframe(data, on_select="rerun", selection_mode="single-row",
                             hide_index=True, use_container_width=True,
                             key=f"mention_table_{st.session_state.get('table_nonce', 0)}",
                             column_config={"Ticket": st.column_config.TextColumn(width="small"),
                                            "Message": st.column_config.TextColumn(width="large")})
        chosen = event.selection.rows
        if chosen:
            item = display[chosen[0]]
            # Existing per-role access control still applies when ticket is opened.
            mark_mentions_read(user, [item["mention_id"]])
            st.session_state.table_nonce = st.session_state.get("table_nonce", 0) + 1
            open_ticket(item["ticket_id"])
        if st.button("Mark all as read", key="mark_all_mentions"):
            mark_mentions_read(user, [item["mention_id"] for item in pending])
            st.rerun()


def add_message(ticket_id, user, role, kind, target, message, recipients=None):
    chat_ws().append_row([now(), str(ticket_id), user, role, kind, target, message.strip()], value_input_option="RAW")
    recipients = extract_mentions(message, recipients or [], user)
    if recipients:
        timestamp = now()
        excerpt = message.strip().replace("\n", " ")[:180]
        mention_ws().append_rows([[uuid.uuid4().hex, timestamp, str(ticket_id), user, email, excerpt]
                                  for email in recipients], value_input_option="RAW")
        load_mentions.clear()
    load_chat.clear()
    log_action(ticket_id, kind.upper(), user, "", "", f"Target: {target}; Mentions: {', '.join(recipients)}")



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
    ticket_ws().update(range_name=f"A{row}:{column_letter(len(HEADERS))}{row}", values=[[str(d.get(h, "")) for h in HEADERS]], value_input_option="RAW")
    invalidate_tickets()


def patch_ticket(ticket_id, changes, allowed_fields=None):
    """Write only owned columns; never rewrite a different team's fields."""
    if allowed_fields is not None and not set(changes).issubset(set(allowed_fields)):
        raise PermissionError("Field ownership violation")
    ws = ticket_ws()
    records = ws.get_all_values()
    if not records or records[0] != HEADERS:
        raise ValueError("Ticket schema mismatch")
    row_num = None
    for idx, row in enumerate(records[1:], 2):
        if row and str(row[0]) == str(ticket_id):
            row_num = idx
            break
    if row_num is None:
        raise ValueError("Ticket not found")
    for key, value in changes.items():
        col = column_letter(HEADERS.index(key) + 1)
        ws.update_acell(f"{col}{row_num}", str(value))
    invalidate_tickets()


def fresh_ticket(ticket_id):
    invalidate_tickets()
    return next((x for x in load_tickets() if x["ticket_id"] == str(ticket_id)), None)


SALES_FIELDS = {
    "source_of_business", "our_client", "marketing_name", "class_of_business",
    "period_from", "period_to", "insured_name", "occupation", "country",
    "province", "city", "risk_detail", "currency", "total_sum_insured",
    "brokerage_ric", "process_reinsurance", "exchange_rate_idr", "sum_insured_idr",
    "premium_rate_pct", "premium_original", "premium_idr", "additional_date", "additional_ps_no",
    "additional_intermediary", "additional_insured", "additional_coverage", "additional_fee"
}


def audit_edit(ticket_id, user, role, changes):
    if not changes:
        return
    changes = dict(changes)
    changes.update(updated_at=now(), updated_by=user)
    patch_ticket(ticket_id, changes, set(changes))
    log_action(ticket_id, f"EDIT_{role.upper().replace(' ', '_')}", user, "", "", ", ".join(changes.keys()))


def open_ticket(ticket_id):
    st.session_state.selected_ticket = str(ticket_id)
    st.rerun()


def page_back():
    st.session_state.table_nonce = st.session_state.get("table_nonce", 0) + 1
    st.session_state.selected_ticket = None
    st.rerun()


def show_table(rows, key, empty_message="Belum ada tiket."):
    """Compact, selectable, paginated native Streamlit table; no external ticket buttons."""
    if not rows:
        st.caption(empty_message)
        return
    search_col, page_size_col = st.columns([5, 1], vertical_alignment="bottom")
    with search_col:
        query = st.text_input(
            "Cari tiket", key=f"{key}_search",
            placeholder="Search ticket number or insured name...",
            label_visibility="collapsed",
        ).strip().casefold()
    with page_size_col:
        page_size = st.selectbox("Rows", [10, 20, 50], index=0, key=f"{key}_size", label_visibility="collapsed")

    filtered = [x for x in rows if not query or query in str(x['ticket_id']).casefold() or query in str(x['insured_name']).casefold()]
    filtered.sort(key=lambda x: int(x['ticket_id']) if str(x['ticket_id']).isdigit() else 0, reverse=True)
    n = len(filtered)
    total_pages = max(1, (n + page_size - 1) // page_size)
    page_key = f"{key}_page"
    signature = (query, page_size)
    if st.session_state.get(f"{key}_signature") != signature:
        st.session_state[page_key] = 1
        st.session_state[f"{key}_signature"] = signature
    current_page = min(max(1, int(st.session_state.get(page_key, 1))), total_pages)
    st.session_state[page_key] = current_page
    left = (current_page - 1) * page_size
    page_rows = filtered[left:left + page_size]
    if not page_rows:
        st.caption("No matching tickets.")
        return

    data = pd.DataFrame([{
        "Ticket No.": f"#{x['ticket_id']}",
        "Insured Name": x['insured_name'] or "—",
        "Class": x['class_of_business'] or "—",
        "Status": x['status'],
        "Last Updated": x['updated_at'],
    } for x in page_rows])
    table_event = st.dataframe(
        data, hide_index=True, use_container_width=True,
        height=min(42 + len(page_rows) * 36, 465),
        on_select="rerun", selection_mode="single-row",
        key=f"{key}_table_p{current_page}_q{abs(hash(signature))}_n{st.session_state.get('table_nonce', 0)}",
        column_config={
            "Ticket No.": st.column_config.TextColumn("TICKET", width="small"),
            "Insured Name": st.column_config.TextColumn("INSURED NAME", width="large"),
            "Class": st.column_config.TextColumn("CLASS", width="small"),
            "Status": st.column_config.TextColumn("STATUS", width="medium"),
            "Last Updated": st.column_config.TextColumn("LAST UPDATED", width="medium"),
        },
    )
    selected_rows = table_event.selection.rows
    if selected_rows:
        selected_row = selected_rows[0]
        if 0 <= selected_row < len(page_rows):
            open_ticket(page_rows[selected_row]['ticket_id'])

    nav1, nav2, nav3, nav4 = st.columns([3, 1, 1, 2], vertical_alignment="center")
    nav1.caption(f"{n:,} tickets · {left + 1}–{left + len(page_rows)} shown")
    with nav2:
        if st.button("Previous", key=f"{key}_prev", disabled=current_page <= 1, use_container_width=True):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with nav3:
        if st.button("Next", key=f"{key}_next", disabled=current_page >= total_pages, use_container_width=True):
            st.session_state[page_key] = current_page + 1
            st.rerun()
    nav4.caption(f"Page {current_page} of {total_pages}")


def safe(x):
    return html.escape(str(x or "—")).replace("\n", "<br/>")


def amount(value, decimals=2):
    """Indonesian monetary grouping, with no unnecessary decimal zeros."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "—"
    raw = f"{number:,.{decimals}f}".rstrip("0").rstrip(".")
    return raw.replace(",", "_").replace(".", ",").replace("_", ".")


def premium_values(currency, sum_insured, rate_pct, exchange_rate):
    """Rate entered as percent (e.g. 0.25 means 0.25%)."""
    multiplier = 1.0 if currency == "IDR" else float(exchange_rate)
    original = float(sum_insured) * float(rate_pct) / 100.0
    return float(sum_insured) * multiplier, original, original * multiplier


def money_details(d):
    curr = d.get("currency", "IDR") or "IDR"
    fx_raw = d.get("exchange_rate_idr", "")
    fx = float(fx_raw) if str(fx_raw).strip() else (1.0 if curr == "IDR" else None)
    tsi = d.get("total_sum_insured", "")
    premium_rate = d.get("premium_rate_pct", "")
    fields = [("Total Sum Insured", f"{curr} {amount(tsi)}")]
    if curr != "IDR":
        fields.append(("Exchange Rate", f"1 {curr} = IDR {amount(fx)}" if fx else "Not recorded"))
        fields.append(("Total Sum Insured (IDR)",
                       f"IDR {amount(d.get('sum_insured_idr') or float(tsi or 0) * fx)}" if fx else "Not recorded"))
    fields.append(("Premium Rate", f"{amount(premium_rate, 6)}%" if str(premium_rate).strip() else "Not recorded"))
    if str(premium_rate).strip():
        _, computed_original, computed_idr = premium_values(curr, tsi, premium_rate, fx or 1)
        fields.append(("Estimated Premium", f"{curr} {amount(d.get('premium_original') or computed_original)}"))
        if curr != "IDR" and fx:
            fields.append(("Estimated Premium (IDR)", f"IDR {amount(d.get('premium_idr') or computed_idr)}"))
    else:
        fields.append(("Estimated Premium", "Not recorded"))
    return fields


def premium_preview(currency, tsi, rate, fx):
    tsi_idr, premium_original, premium_idr = premium_values(currency, tsi, rate, fx)
    st.markdown("**Premium Calculation**")
    if currency == "IDR":
        a, b = st.columns(2)
        a.metric("Total Sum Insured", f"IDR {amount(tsi)}")
        b.metric("Estimated Premium", f"IDR {amount(premium_original)}")
    else:
        a, b, c = st.columns(3)
        a.metric(f"Sum Insured ({currency})", f"{currency} {amount(tsi)}")
        b.metric("Sum Insured (IDR)", f"IDR {amount(tsi_idr)}")
        c.metric(f"Premium ({currency})", f"{currency} {amount(premium_original)}")
        st.caption(f"Estimated Premium (IDR): IDR {amount(premium_idr)} · 1 {currency} = IDR {amount(fx)}")
    st.caption("Premium = Sum Insured × Premium Rate (%). Indicative gross premium before any additional fees or adjustments.")
    return tsi_idr, premium_original, premium_idr


def pdf_bytes(d):
    """Premium A4 acceptance record with consistent hierarchy and page folios."""
    buff = io.BytesIO()
    navy = colors.HexColor("#102C49")
    blue = colors.HexColor("#1760AE")
    ink = colors.HexColor("#1C3249")
    muted = colors.HexColor("#6C7F92")
    border = colors.HexColor("#DDE6EF")
    soft = colors.HexColor("#F3F7FB")
    doc = SimpleDocTemplate(buff, pagesize=A4, leftMargin=43, rightMargin=43,
                            topMargin=53, bottomMargin=52, title=f"SuperDashboard Ticket {d['ticket_id']}",
                            author="SuperDashboard")
    avail = A4[0] - 86
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SD_Title", parent=styles["Normal"], fontName="Helvetica-Bold",
                              fontSize=20, leading=25, textColor=navy, spaceAfter=3))
    styles.add(ParagraphStyle(name="SD_Sub", parent=styles["Normal"], fontSize=9, leading=13,
                              textColor=muted))
    styles.add(ParagraphStyle(name="SD_H", parent=styles["Normal"], fontName="Helvetica-Bold",
                              fontSize=10.5, leading=15, textColor=navy, spaceBefore=12, spaceAfter=7))
    styles.add(ParagraphStyle(name="SD_Label", parent=styles["Normal"], fontName="Helvetica-Bold",
                              fontSize=8, leading=12, textColor=muted))
    styles.add(ParagraphStyle(name="SD_Value", parent=styles["Normal"], fontSize=9, leading=14,
                              textColor=ink, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="SD_Value_Bold", parent=styles["SD_Value"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="SD_Muted", parent=styles["Normal"], fontSize=8, leading=12, textColor=muted))
    styles.add(ParagraphStyle(name="SD_Metric", parent=styles["Normal"], fontName="Helvetica-Bold",
                              fontSize=16, leading=20, textColor=navy))

    def P(value, sty="SD_Value"):
        return Paragraph(safe(value), styles[sty])

    def pairs_section(title, pairs):
        # One visual table per section, with alternating lightly colored rows.
        story.append(Paragraph(safe(title.upper()), styles["SD_H"]))
        content = []
        for label, value in pairs:
            content.append([P(label, "SD_Label"), P(value)])
        tbl = Table(content, colWidths=[155, avail - 155], hAlign="LEFT")
        ts = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("LINEBELOW", (0, 0), (-1, -2), .35, border),
            ("BOX", (0, 0), (-1, -1), .6, border),
            ("BACKGROUND", (0, 0), (0, -1), soft),
        ]
        tbl.setStyle(TableStyle(ts))
        story.append(tbl)

    story = []
    # Executive masthead: disciplined whitespace with branded accent line.
    top = Table([[P("SUPERDASHBOARD", "SD_Title"), P("#BePaperless", "SD_Muted")]],
                colWidths=[avail * .73, avail * .27])
    top.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "BOTTOM"),
                             ("ALIGN", (1,0), (1,0), "RIGHT"),
                             ("LEFTPADDING", (0,0), (-1,-1), 0),
                             ("RIGHTPADDING", (0,0), (-1,-1), 0),
                             ("BOTTOMPADDING", (0,0), (-1,-1), 7)]))
    story.append(top)
    story.append(HRFlowable(width="100%", thickness=2.5, color=blue, spaceAfter=11))
    story.append(P("ACCEPTANCE & QUOTATION RECORD", "SD_Sub"))
    story.append(Spacer(1, 11))
    headline = Table([
        [P("TICKET NUMBER", "SD_Label"), P("CURRENT STATUS", "SD_Label"), P("LAST UPDATED", "SD_Label")],
        [P(f"#{d['ticket_id']}", "SD_Value_Bold"), P(d['status'], "SD_Value_Bold"), P(d['updated_at'] or d['created_at'])],
    ], colWidths=[avail *.23, avail *.32, avail *.45])
    headline.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), soft),
                                  ("BOX", (0,0), (-1,-1), .8, border),
                                  ("TOPPADDING", (0,0), (-1,0), 9),
                                  ("BOTTOMPADDING", (0,1), (-1,1), 10),
                                  ("LEFTPADDING", (0,0), (-1,-1), 12),
                                  ("RIGHTPADDING", (0,0), (-1,-1), 9)]))
    story.append(headline)

    pairs_section("01 / Business & Policy Details", [
        ("Source of Business", d['source_of_business']), ("Our Client", d.get("our_client", "")), ("Marketing Name", d['marketing_name']),
        ("Class of Business", d['class_of_business']),
        ("Period of Insurance", f"{d['period_from']} — {d['period_to']}"),
        ("Insured Name", d['insured_name']), ("Occupation", d['occupation']),
        ("Risk Location", ", ".join(str(d[k]) for k in ['risk_detail', 'city', 'province', 'country'] if d[k])),
        *money_details(d),
        ("Brokerage / RIC", f"{d['currency']} {amount(d['brokerage_ric'])}"),
        ("Reinsurance Required", "Yes" if d['process_reinsurance'] == 'Yes' else "No"),
        ("Renewal Business", "Yes" if d.get('renewal_business') == 'Yes' else "No"),
    ])

    story.append(Paragraph("02 / ACTUARIAL INSIGHT", styles["SD_H"]))
    metric = Table([
        [P("LOSS RATIO", "SD_Label"), P("COMBINED RATIO", "SD_Label")],
        [P("—", "SD_Metric"), P("—", "SD_Metric")],
        [P("Awaiting actuarial data", "SD_Muted"), P("Awaiting actuarial data", "SD_Muted")],
    ], colWidths=[avail/2, avail/2])
    metric.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,-1),soft),
                               ("BOX", (0,0),(-1,-1),.7,border),
                               ("LINEBEFORE", (1,0),(1,-1),.7,border),
                               ("LEFTPADDING",(0,0),(-1,-1),12),
                               ("TOPPADDING",(0,0),(-1,0),10),
                               ("BOTTOMPADDING",(0,-1),(-1,-1),11)]))
    story.append(metric)

    pairs_section("03 / Marketing Information", [
        ("Marketing Information", d['marketing_information']),
        ("Filled by", f"{d['created_by']} at {d['sales_confirmed_at']}"),
        ("Reviewed by Marketing", f"{d['marketing_reviewed_by']} at {d['marketing_reviewed_at']}" if d['marketing_reviewed_at'] else "Pending"),
    ])
    if d['process_reinsurance'] == 'Yes':
        pairs_section("04 / Reinsurance Review", [
            ("Reinsurance Information", d['reinsurance_information']),
            ("Reviewed by Reinsurance", f"{d['reinsurance_reviewed_by']} at {d['reinsurance_reviewed_at']}" if d['reinsurance_reviewed_at'] else "Pending"),
        ])
    pairs_section("05 / Underwriting Decision", [
        ("Final Decision", d['uw_status']), ("Our Role", d['our_role']),
        ("Our Share (%)", d['our_share_pct']),
        ("Underwriting Recommendation", d['underwriting_recommendation']),
        ("Own Retention (%)", d['own_retention_pct']),
        ("Treaty QS (%)", d['qs_pct']), ("Treaty SPL (%)", d['spl_pct']),
        ("Facultative (%)", d['facultative_pct']),
        ("Allocation Total (%)", d['allocation_total_pct']),
        ("Reviewed / Approved by Underwriting", f"{d['uw_confirmed_by']} at {d['uw_confirmed_at']}" if d['uw_confirmed_at'] else "Pending"),
    ])
    if d.get('additional_form') == 'Yes':
        pairs_section("06 / Additional Form", [
            ("Date", d.get('additional_date', '')), ("PS No", d.get('additional_ps_no', '')),
            ("Name of Intermediary", d.get('additional_intermediary', '')),
            ("Name of Insured", d.get('additional_insured', '')),
            ("Coverage", d.get('additional_coverage', '')),
            ("Total of Additional Fee", f"{d.get('currency','IDR')} {amount(d.get('additional_fee'))}"),
            ("Approval Status", d.get('additional_status', '')),
        ])
        story.append(Paragraph("SIGNATURE REGISTER", styles["SD_H"]))
        sig_fields = [
            ("Sales Support", 'additional_sales_signed_by', 'additional_sales_signed_at'),
            ("Marketing Manager", 'additional_marketing_signed_by', 'additional_marketing_signed_at'),
            ("Marketing Director", 'additional_marketing_director_signed_by', 'additional_marketing_director_signed_at'),
            ("Technical Director", 'additional_technical_signed_by', 'additional_technical_signed_at'),
            ("President Director", 'additional_president_signed_by', 'additional_president_signed_at'),
        ]
        cells = []
        for label, by, at in sig_fields:
            signed = f"Signed by {d.get(by)} at {d.get(at)}" if d.get(by) else "Awaiting signature"
            cells.append([P(label, 'SD_Label'), P(signed, 'SD_Value')])
        sig_table = Table(cells, colWidths=[155, avail - 155])
        sig_table.setStyle(TableStyle([
            ('BOX', (0,0),(-1,-1),.6,border),
            ('LINEBELOW', (0,0),(-1,-2),.35,border),
            ('BACKGROUND',(0,0),(0,-1),soft),
            ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9),
        ]))
        story.append(sig_table)
    # Attachment metadata is included; binary documents are available in the app.
    attachments = load_attachment_manifest(d["ticket_id"])
    document_links = load_attachment_links(d["ticket_id"])
    if attachments or document_links:
        pairs_section("07 / Supporting Documents", [
            (f"{item['category']}", f"{item['filename']} · uploaded by {item['uploaded_by']} at {item['uploaded_at']}")
            for item in attachments
        ] + [
            (f"{item['category']}", f"{item['label']} · Google Drive link · {item['uploaded_by']}")
            for item in document_links
        ])
    story.append(Spacer(1,14))
    story.append(P("Internal workflow record. This document does not constitute a policy, cover note, or binder.", "SD_Muted"))

    def page_footer(canvas, doc_obj):
        canvas.saveState()
        width, _ = A4
        canvas.setStrokeColor(border)
        canvas.setLineWidth(.6)
        canvas.line(43, 40, width - 43, 40)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(43, 28, f"SuperDashboard  |  #{d['ticket_id']}  |  Generated {now()}")
        canvas.drawRightString(width - 43, 28, f"Page {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return buff.getvalue()


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


def signature_card(label, signed_by="", signed_at=""):
    sign = f"Signed by {html.escape(str(signed_by))}<br><span>{html.escape(str(signed_at))}</span>" if signed_by else "Awaiting signature"
    st.markdown(f"<div class='signature-card'><div class='signature-role'>{html.escape(label)}</div>"
                f"<div class='signature-value'>{sign}</div></div>", unsafe_allow_html=True)


def additional_form_preview(d):
    st.markdown("#### Additional Form")
    st.caption(f"Approval status: {d.get('additional_status') or 'Pending Marketing'}")
    a, b, c = st.columns(3)
    a.text_input("Date", value=d.get("additional_date", ""), disabled=True, key="view_add_date")
    b.text_input("PS No", value=d.get("additional_ps_no", ""), disabled=True, key="view_add_ps")
    c.text_input("Total Additional Fee", value=d.get("additional_fee", ""), disabled=True, key="view_add_fee")
    left, right = st.columns(2)
    with left:
        st.text_input("Name of Intermediary", value=d.get("additional_intermediary", ""), disabled=True)
        st.text_input("Coverage", value=d.get("additional_coverage", ""), disabled=True)
    with right:
        st.text_input("Name of Insured", value=d.get("additional_insured", ""), disabled=True)
    sigs = [
        ("Sales Support", "additional_sales_signed_by", "additional_sales_signed_at"),
        ("Marketing Manager", "additional_marketing_signed_by", "additional_marketing_signed_at"),
        ("Marketing Director", "additional_marketing_director_signed_by", "additional_marketing_director_signed_at"),
        ("Technical Director", "additional_technical_signed_by", "additional_technical_signed_at"),
        ("President Director", "additional_president_signed_by", "additional_president_signed_at"),
    ]
    for i in range(0, len(sigs), 3):
        columns = st.columns(3)
        for col, (label, by, at) in zip(columns, sigs[i:i+3]):
            with col:
                signature_card(label, d.get(by, ""), d.get(at, ""))


def chat_panel(d, role, user):
    with st.expander("Ticket Discussion & Revision Requests", expanded=False):
        messages = load_chat(d["ticket_id"])
        if messages:
            for m in messages[-40:]:
                label = f"{m['role']} · {m['username']} · {m['timestamp']}"
                if m.get('type') == 'Revision Request':
                    label += f" · Revision requested from {m['target_role']}"
                st.markdown(f"**{html.escape(label)}**")
                st.write(m.get("message", ""))
                st.divider()
        else:
            st.caption("No messages yet.")
        with st.form(f"chat_{d['ticket_id']}", clear_on_submit=True):
            msg = st.text_area("Message", placeholder="Write a message; mention colleagues with @gilang.k or @hadi...", height=85)
            recipients = st.multiselect(
                "Mention people (in-app notification)",
                options=[email for email in ROLES if email != user],
                format_func=lambda email: f"{ROLES[email]} · {email}",
                help="Selected colleagues and @mentioned usernames receive a dashboard notification.",
            )
            c1, c2 = st.columns(2)
            with c1:
                kind = st.selectbox("Message type", ["Discussion", "Revision Request"])
            with c2:
                target = st.selectbox("For team", ["All Teams", "Sales Support", "Marketing", "Reinsurance", "Underwriting", "Technical Director"])
            send = st.form_submit_button("Send Message", type="primary")
        if send and msg.strip():
            add_message(d['ticket_id'], user, role, kind, target, msg, recipients)
            st.rerun()


def new_ticket(user):
    st.subheader("Create New Acceptance Ticket")
    st.caption("Complete quotation details • Fields marked * are mandatory")
    # Dynamic locations outside form: changes update dependent city selector immediately.
    lcol, rcol = st.columns(2, gap="large")
    with lcol:
        src = st.selectbox("Source of Business *", SOURCES)
        if src != "Direct Business":
            our_client = st.text_input("Our Client *")
            marketing_name = st.text_input("Marketing Name *")
        else:
            our_client = ""
            marketing_name = ""
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
    renewal = st.checkbox("Renewal Business", key="renewal_business_toggle")
    if renewal:
        previous_documents = st.file_uploader("Upload Previous Document", type=sorted(ALLOWED_EXTENSIONS),
            accept_multiple_files=True, key="previous_docs")
    else:
        previous_documents = []
    additional = st.checkbox("Make an Additional Form", key="additional_form_toggle")
    st.markdown("#### Sum Insured & Premium")
    money_l, money_r = st.columns(2, gap="large")
    with money_l:
        currency = st.selectbox("Currency *", CURRENCIES, key="new_currency")
        sum_insured = st.number_input("Total Sum Insured *", min_value=0.0, step=1000000.0,
                                      format="%.2f", key="new_tsi")
    with money_r:
        premium_rate = st.number_input("Premium Rate (%) *", min_value=0.0, max_value=100.0,
                                       step=0.01, format="%.6f", key="new_premium_rate",
                                       help="Contoh: isi 0.25 untuk rate 0,25%")
        fx = (st.number_input(f"Exchange Rate · 1 {currency} = IDR *", min_value=0.000001,
                              value=16000.0 if currency == "USD" else 1.0,
                              step=1.0, format="%.4f", key=f"new_fx_{currency}")
              if currency != "IDR" else 1.0)
    tsi_idr, premium_original, premium_idr = premium_preview(currency, sum_insured, premium_rate, fx)
    with st.form("new_ticket", clear_on_submit=False):
        st.markdown("#### Business & Policy Details")
        c1, c2 = st.columns(2, gap="large")
        with c1:
            class_of_business = st.selectbox("Class of Business *", CLASSES)
            insured = st.text_input("Insured Name *")
            period_from = st.date_input("Period of Insurance — From *")
        with c2:
            occupation = st.text_input("Occupation *")
            detail = st.text_input("Risk Location — Detail *")
            period_to = st.date_input("Period of Insurance — Up to *")
            brokerage = st.number_input("Brokerage / RIC", min_value=0.0, step=100000.0, format="%.2f")
            to_reins = st.checkbox("Proses Tiket ke Reasuransi")
        additional_inputs = {}
        if additional:
            st.markdown("#### Additional Form Details")
            ac1, ac2 = st.columns(2)
            with ac1:
                additional_inputs["additional_date"] = str(st.date_input("Date", value=datetime.now(TZ).date()))
                additional_inputs["additional_ps_no"] = st.text_input("PS No")
                additional_inputs["additional_intermediary"] = st.text_input("Name of Intermediary")
            with ac2:
                additional_inputs["additional_insured"] = st.text_input("Name of Insured", value=insured)
                additional_inputs["additional_coverage"] = st.text_input("Coverage")
                additional_inputs["additional_fee"] = f"{st.number_input('Total of Additional Fee', min_value=0.0, format='%.2f'):.2f}"
        st.markdown("#### Supporting Documents")
        supporting_documents = st.file_uploader("Upload supporting documents", type=sorted(ALLOWED_EXTENSIONS),
            accept_multiple_files=True, key="supporting_docs")
        upload_limit_note()
        drive_url_new = st.text_input("Google Drive link (optional)", placeholder="https://drive.google.com/file/d/...")
        drive_label_new = st.text_input("Google Drive document name (optional)")
        actuarial_insight()
        st.markdown("#### Marketing Information")
        marketing_info = st.text_area("Information & Explanation *", height=125, label_visibility="collapsed", placeholder="Provide marketing background, client context and quotation notes...")
        declaration = st.checkbox("Saya menyatakan bahwa informasi yang saya isi sudah benar")
        submit = st.form_submit_button("Process Ticket →", type="primary", use_container_width=True)
    if submit:
        errors, all_uploads = validate_uploads(renewal, previous_documents, supporting_documents)
        if all_uploads and not drive_folder_ready():
            errors.append("Upload file memerlukan drive_folder_id (Shared Drive) pada Secrets. Alternatif: upload ke Google Drive manual dan isi link dokumen.")
        if drive_url_new.strip() and not valid_drive_link(drive_url_new):
            errors.append("Link Google Drive tidak valid.")
        if src != "Direct Business" and not marketing_name.strip():
            errors.append("Marketing Name wajib diisi untuk source yang dipilih.")
        if src != "Direct Business" and not our_client.strip():
            errors.append("Our Client wajib diisi untuk non-direct business.")
        if additional and any(not str(additional_inputs.get(k, "")).strip() for k in ["additional_ps_no", "additional_intermediary", "additional_insured", "additional_coverage"]):
            errors.append("Lengkapi seluruh informasi Additional Form.")
        if period_to < period_from:
            errors.append("Tanggal Up to harus sama atau sesudah From.")
        if not insured.strip() or not occupation.strip() or not detail.strip() or not marketing_info.strip() or not province.strip() or not city.strip():
            errors.append("Insured, Occupation, Province, City, Risk Detail, dan Marketing Information wajib diisi.")
        if sum_insured <= 0:
            errors.append("Total Sum Insured harus lebih dari nol.")
        if premium_rate <= 0:
            errors.append("Premium Rate harus lebih dari nol.")
        if currency != "IDR" and fx <= 0:
            errors.append("Exchange Rate harus lebih dari nol.")
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
            "our_client": our_client,
            "renewal_business": "Yes" if renewal else "No",
            "additional_form": "Yes" if additional else "No",
            "additional_status": "Pending Marketing" if additional else "",
            "additional_sales_signed_by": user if additional else "",
            "additional_sales_signed_at": stamp if additional else "",
            "class_of_business": class_of_business, "period_from": str(period_from), "period_to": str(period_to),
            "insured_name": insured, "occupation": occupation,
            "country": country, "province": province,
            "city": city, "risk_detail": detail,
            "currency": currency, "total_sum_insured": f"{sum_insured:.2f}",
            "exchange_rate_idr": f"{fx:.6f}", "sum_insured_idr": f"{tsi_idr:.2f}",
            "premium_rate_pct": f"{premium_rate:.6f}", "premium_original": f"{premium_original:.2f}",
            "premium_idr": f"{premium_idr:.2f}",
            "brokerage_ric": f"{brokerage:.2f}", "process_reinsurance": "Yes" if to_reins else "No",
            "marketing_information": marketing_info, "sales_confirmed_at": stamp,
            "updated_at": stamp, "updated_by": user
        })
        d.update(additional_inputs)
        append_ticket(d)
        log_action(tid, "CREATE", user, "", "Pending Marketing", "Ticket created by Sales Support")
        failed = []
        for category, uploaded_file in all_uploads:
            try:
                save_attachment(tid, category, uploaded_file, user)
            except Exception as exc:
                failed.append(f"{uploaded_file.name}: {exc}")
        if drive_url_new.strip():
            try:
                save_attachment_link(tid, "Supporting Document", drive_label_new or "Google Drive document", drive_url_new, user)
            except Exception as exc:
                failed.append(f"Google Drive link: {exc}")
        if failed:
            st.error("Ticket tersimpan, tetapi sebagian dokumen gagal diunggah. " + " | ".join(failed))
        else:
            st.success(f"Ticket #{tid} berhasil dibuat. Status: Pending Marketing")
        st.session_state.selected_ticket = tid
        st.rerun()


def edit_owned_fields(d, role, user):
    """Section-owner edits, independent of current workflow state; audit every update."""
    if role == "Sales Support" and d["created_by"] == user:
        with st.expander("Edit Sales Support Information", expanded=False):
            st.markdown("**Sum Insured & Premium**")
            keyprefix = f"edit_{d['ticket_id']}"
            mx, my = st.columns(2)
            with mx:
                currency = st.selectbox("Currency", CURRENCIES,
                    index=CURRENCIES.index(d['currency']) if d['currency'] in CURRENCIES else 0,
                    key=f"{keyprefix}_currency")
                tsi = st.number_input("Total Sum Insured", value=float(d.get('total_sum_insured') or 0),
                                      min_value=0.0, format="%.2f", key=f"{keyprefix}_tsi")
            with my:
                rate = st.number_input("Premium Rate (%)", value=float(d.get('premium_rate_pct') or 0),
                                       min_value=0.0, max_value=100.0, step=0.01,
                                       format="%.6f", key=f"{keyprefix}_rate")
                fx_default = float(d.get('exchange_rate_idr') or (16000.0 if currency == "USD" else 1.0))
                fx = (st.number_input(f"Exchange Rate · 1 {currency} = IDR",
                        value=fx_default if d.get('currency') == currency else (16000.0 if currency == 'USD' else 1.0),
                        min_value=0.000001, format="%.4f", key=f"{keyprefix}_fx_{currency}")
                      if currency != "IDR" else 1.0)
            tsi_idr, premium_original, premium_idr = premium_preview(currency, tsi, rate, fx)
            with st.form(f"sales_edit_{d['ticket_id']}"):
                a, b = st.columns(2)
                with a:
                    src = st.selectbox("Source of Business", SOURCES, index=SOURCES.index(d['source_of_business']) if d['source_of_business'] in SOURCES else 0)
                    client = st.text_input("Our Client", d.get("our_client", "")) if src != "Direct Business" else ""
                    mkt = st.text_input("Marketing Name", d.get("marketing_name", "")) if src != "Direct Business" else ""
                    cob = st.selectbox("Class", CLASSES, index=CLASSES.index(d['class_of_business']) if d['class_of_business'] in CLASSES else 0)
                    insured = st.text_input("Insured Name", d['insured_name'])
                    occupation = st.text_input("Occupation", d['occupation'])
                with b:
                    date_from = st.date_input("Period From", value=datetime.fromisoformat(d['period_from']).date())
                    date_to = st.date_input("Period To", value=datetime.fromisoformat(d['period_to']).date())
                    country = st.text_input("Country", d['country'])
                    province = st.text_input("Province", d['province'])
                    city = st.text_input("City", d['city'])
                    detail = st.text_input("Risk Location Detail", d['risk_detail'])
                    ric = st.number_input("Brokerage / RIC", value=float(d.get('brokerage_ric') or 0), min_value=0.0, format="%.2f")
                    reins = st.checkbox("Proses Tiket ke Reasuransi", value=d.get('process_reinsurance') == 'Yes', disabled=bool(d.get('marketing_reviewed_at')))
                # Lock reinsurance routing after marketing has decided the next stage.
                extra = {}
                if d.get("additional_form") == "Yes":
                    st.markdown("**Additional Form Details**")
                    ex1, ex2 = st.columns(2)
                    with ex1:
                        extra['additional_ps_no'] = st.text_input("PS No", d.get('additional_ps_no', ''))
                        extra['additional_intermediary'] = st.text_input("Name of Intermediary", d.get('additional_intermediary', ''))
                        extra['additional_date'] = str(st.date_input("Additional Date", value=datetime.fromisoformat(d['additional_date']).date() if d.get('additional_date') else datetime.now(TZ).date()))
                    with ex2:
                        extra['additional_insured'] = st.text_input("Name of Insured", d.get('additional_insured', ''))
                        extra['additional_coverage'] = st.text_input("Coverage", d.get('additional_coverage', ''))
                        extra['additional_fee'] = f"{st.number_input('Total Additional Fee', value=float(d.get('additional_fee') or 0), min_value=0.0, format='%.2f'):.2f}"
                save = st.form_submit_button("Save Changes")
            if save:
                if not all([insured.strip(), occupation.strip(), detail.strip(), city.strip(), province.strip(), country.strip()]) or tsi <= 0 or rate <= 0 or date_to < date_from:
                    st.error("Periksa isian wajib, nilai TSI, dan periode asuransi.")
                elif src != "Direct Business" and not (client.strip() and mkt.strip()):
                    st.error("Our Client dan Marketing Name wajib diisi untuk non-direct business.")
                else:
                    changes = dict(source_of_business=src, our_client=client, marketing_name=mkt,
                        class_of_business=cob, insured_name=insured, occupation=occupation,
                        currency=currency, total_sum_insured=f"{tsi:.2f}",
                        exchange_rate_idr=f"{fx:.6f}", sum_insured_idr=f"{tsi_idr:.2f}",
                        premium_rate_pct=f"{rate:.6f}", premium_original=f"{premium_original:.2f}",
                        premium_idr=f"{premium_idr:.2f}", period_from=str(date_from),
                        period_to=str(date_to), country=country, province=province, city=city,
                        risk_detail=detail, brokerage_ric=f"{ric:.2f}")
                    if not d.get('marketing_reviewed_at'):
                        changes['process_reinsurance'] = 'Yes' if reins else 'No'
                    changes.update(extra)
                    audit_edit(d['ticket_id'], user, role, changes)
                    st.rerun()
    elif role == "Marketing":
        with st.expander("Edit Marketing Information", expanded=False):
            with st.form(f"marketing_edit_{d['ticket_id']}"):
                info = st.text_area("Marketing Information", value=d.get('marketing_information', ''), height=120)
                save = st.form_submit_button("Save Changes")
            if save and info.strip():
                audit_edit(d['ticket_id'], user, role, {'marketing_information': info})
                st.rerun()
    elif role == "Reinsurance" and d.get('process_reinsurance') == 'Yes' and d.get('marketing_reviewed_at'):
        with st.expander("Edit Reinsurance Information", expanded=False):
            with st.form(f"reins_edit_{d['ticket_id']}"):
                info = st.text_area("Reinsurance Information", value=d.get('reinsurance_information', ''), height=120)
                save = st.form_submit_button("Save Changes")
            if save:
                audit_edit(d['ticket_id'], user, role, {'reinsurance_information': info})
                st.rerun()
    elif role == "Underwriting" and d.get('uw_confirmed_by'):
        with st.expander("Edit Underwriting Information", expanded=False):
            with st.form(f"uw_edit_{d['ticket_id']}"):
                a, b, c = st.columns(3)
                with a:
                    decision = st.selectbox("Decision", FINAL_STATUSES, index=FINAL_STATUSES.index(d['uw_status']) if d['uw_status'] in FINAL_STATUSES else 0)
                with b:
                    leader = st.selectbox("Our Role", ["Leader", "Member"], index=0 if d['our_role'] != "Member" else 1)
                with c:
                    share = st.number_input("Our Share (%)", value=float(d.get('our_share_pct') or 100), min_value=0.0, max_value=100.0)
                rec = st.text_area("Underwriting Recommendation", value=d.get('underwriting_recommendation', ''))
                c1, c2, c3, c4 = st.columns(4)
                values = [float(d.get(k) or 0) for k in ['own_retention_pct','qs_pct','spl_pct','facultative_pct']]
                own = c1.number_input("Own Retention", value=values[0], min_value=0.0, max_value=100.0)
                qs = c2.number_input("Treaty QS", value=values[1], min_value=0.0, max_value=100.0)
                spl = c3.number_input("Treaty SPL", value=values[2], min_value=0.0, max_value=100.0)
                fac = c4.number_input("Facultative", value=values[3], min_value=0.0, max_value=100.0)
                st.caption(f"Allocation Total: {own+qs+spl+fac:.2f}%")
                save = st.form_submit_button("Save Changes")
            if save:
                if abs(own+qs+spl+fac-100)>0.001 or not rec.strip():
                    st.error("Risk Allocation harus 100% dan recommendation harus diisi.")
                else:
                    audit_edit(d['ticket_id'], user, role, {'status':decision,'uw_status':decision,
                        'our_role':leader,'our_share_pct':f'{share:.2f}', 'underwriting_recommendation':rec,
                        'own_retention_pct':f'{own:.2f}', 'qs_pct':f'{qs:.2f}',
                        'spl_pct':f'{spl:.2f}', 'facultative_pct':f'{fac:.2f}',
                        'allocation_total_pct':f'{own+qs+spl+fac:.2f}'})
                    st.rerun()


def additional_approval(d, role, user):
    if d.get('additional_form') != 'Yes':
        return
    status = d.get('additional_status', '')
    if role == 'Marketing' and status == 'Pending Marketing':
        if st.button("Sign Additional Form & Proceed to Technical Director", type="primary", key=f"add_marketing_{d['ticket_id']}"):
            current = fresh_ticket(d['ticket_id'])
            if current and current.get('additional_status') == 'Pending Marketing':
                stamp = now()
                patch_ticket(d['ticket_id'], {'additional_marketing_signed_by':user,
                    'additional_marketing_signed_at':stamp,
                    'additional_status':'Pending Technical Director', 'updated_at':stamp, 'updated_by':user})
                log_action(d['ticket_id'], 'ADDITIONAL_MARKETING_SIGN', user, status, 'Pending Technical Director')
                st.rerun()
    elif role == 'Technical Director' and status == 'Pending Technical Director':
        if st.button("Sign Additional Form & Confirm", type="primary", key=f"add_technical_{d['ticket_id']}"):
            current = fresh_ticket(d['ticket_id'])
            if current and current.get('additional_status') == 'Pending Technical Director':
                stamp = now()
                patch_ticket(d['ticket_id'], {'additional_technical_signed_by':user,
                    'additional_technical_signed_at':stamp, 'additional_status':'Completed',
                    'updated_at':stamp, 'updated_by':user})
                log_action(d['ticket_id'], 'ADDITIONAL_TECHNICAL_SIGN', user, status, 'Completed')
                st.rerun()


def detail_ticket(d, role, user):
    st.button("← Back to Dashboard", on_click=page_back)
    st.subheader(f"Ticket #{d['ticket_id']} — {d['insured_name']}")
    st.caption("SuperDashboard  ·  #BePaperless")
    st.info(f"Current Status: {d['status']}")
    if d.get("renewal_business") == "Yes":
        st.caption("Renewal Business")
    attachment_panel(d["ticket_id"], role, user,
                     allow_upload=(role == "Sales Support" and d.get("created_by") == user),
                     renewal_ticket=(d.get("renewal_business") == "Yes"))
    details = money_details(d)
    with st.expander("Sum Insured & Premium", expanded=True):
        for label, value in details:
            st.markdown(f"**{label}:** {value}")
    if d.get("source_of_business") != "Direct Business":
        st.caption(f"Our Client: {d.get('our_client', '—')} · Marketing Name: {d.get('marketing_name', '—')}")
    if d.get("additional_form") == "Yes":
        additional_form_preview(d)
    chat_panel(d, role, user)
    edit_owned_fields(d, role, user)
    additional_approval(d, role, user)
    actuarial_insight()
    if st.toggle("Show PDF preview / download", value=False, key=f"pdf_{d['ticket_id']}"):
        pdf = pdf_bytes(d)
        st.download_button("download pdf", pdf, file_name=f"SuperDashboard_Ticket_{d['ticket_id']}.pdf", mime="application/pdf", type="primary")
        st.pdf(pdf, height=560)
    if role in ("Admin", "Technical Director", "Marketing Director", "President Director"):
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
            patch_ticket(d["ticket_id"], {k: current[k] for k in
                ["marketing_information", "marketing_reviewed_by", "marketing_reviewed_at", "status", "updated_at", "updated_by"]})
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
            patch_ticket(d["ticket_id"], {k: current[k] for k in
                ["reinsurance_information", "reinsurance_reviewed_by", "reinsurance_reviewed_at", "status", "updated_at", "updated_by"]})
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
            patch_ticket(d["ticket_id"], {k: current[k] for k in
                ["uw_status", "status", "our_role", "our_share_pct", "underwriting_recommendation",
                 "own_retention_pct", "qs_pct", "spl_pct", "facultative_pct", "allocation_total_pct",
                 "uw_confirmed_by", "uw_confirmed_at", "updated_at", "updated_by"]})
            log_action(d["ticket_id"], "UW_FINAL", user, "Pending UW", decision, f"Allocation {total:.2f}%")
            st.success(f"Tiket selesai: {decision}")
            st.rerun()


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
        if role == "Technical Director" and record.get("additional_form") != "Yes":
            st.error("Akses tidak diizinkan.")
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
    notification_panel(user, all_tickets)
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
        st.subheader("Additional Forms — Awaiting Signature")
        show_table([x for x in all_tickets if x.get('additional_status') == 'Pending Marketing'], "add_marketing_pending")
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
    elif role == "Technical Director":
        st.subheader("Additional Forms — Pending Technical Director")
        show_table([x for x in all_tickets if x.get('additional_status') == 'Pending Technical Director'], "technical_pending")
        st.subheader("Additional Forms — Signed")
        show_table([x for x in all_tickets if x.get('additional_technical_signed_at')], "technical_done")
    elif role in ("Marketing Director", "President Director"):
        st.subheader("Additional Forms — Overview")
        show_table([x for x in all_tickets if x.get('additional_form') == 'Yes'], "director_overview")
    else:
        st.subheader("All Tickets — Admin Overview")
        show_table(all_tickets, "admin_all")
        st.subheader("Status Summary")
        if all_tickets:
            counts = pd.Series([x["status"] for x in all_tickets]).value_counts()
            st.bar_chart(counts)
        st.info("Full audit trail is stored in the AuditLog worksheet in Google Sheets.")
    if st.button("Refresh", key="refresh_data"):
        invalidate_tickets()
        load_mentions.clear()
        load_chat.clear()
        st.rerun()


if __name__ == "__main__":
    main()
