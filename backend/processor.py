import os
import io
import csv
import re
import datetime

def parse_date(s):
    """Parse common date formats and return datetime.date or None."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None

def compute_status(due_date):
    """Compute status string based on due_date."""
    if due_date is None:
        return "incomplete:info"
    today = datetime.date.today()
    delta = (due_date - today).days
    if delta < 0:
        return "non_compliant:critical"
    if delta <= 30:
        return "at_risk:warning"
    return "compliant:good"

def extract_text_from_file(file_bytes):
    """Return text extracted from PDF, Excel, or plain text/CSV."""
    # Try PDF first with pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            if text.strip():
                return text
    except Exception:
        pass

    # Try Excel with openpyxl
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        rows = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    rows.append(",".join(str(cell) if cell is not None else "" for cell in row))
        wb.close()
        text = "\n".join(rows)
        if text.strip():
            return text
    except Exception:
        pass

    # Fallback: decode as UTF-8 text/CSV
    return file_bytes.decode('utf-8', errors='ignore')

def parse_tabular(text):
    """Parse delimited text into list of dicts using csv.Sniffer."""
    try:
        sample = text[:1024]
        dialect = csv.Sniffer().sniff(sample, delimiters=',\t;|')
        has_header = csv.Sniffer().has_header(sample)
    except Exception:
        return None

    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return None

    if has_header:
        header = [h.strip() for h in rows[0]]
        data_rows = rows[1:]
    else:
        header = [f"column_{i}" for i in range(len(rows[0]))]
        data_rows = rows

    records = []
    for row in data_rows:
        if not row or all(cell.strip() == "" for cell in row):
            continue
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))
        elif len(row) > len(header):
            row = row[:len(header)]
        rec = {header[i]: row[i].strip() for i in range(len(header))}
        records.append(rec)
    return records if records else None

def guess_title_key(record):
    """Pick the most likely primary entity field (driver name, etc.)."""
    keys = list(record.keys())
    if not keys:
        return None
    for keyword in ('driver_name', 'name', 'employee_name', 'vendor_name', 'contract_party', 'patient_name', 'title'):
        for k in keys:
            if keyword in k.lower():
                return k
    return keys[0]

def guess_due_date_key(record):
    """Pick the most likely due/expiration date field."""
    keys = list(record.keys())
    if not keys:
        return None
    for keyword in ('expiration', 'expires', 'due_date', 'due', 'expiry', 'expiration_date'):
        for k in keys:
            if keyword in k.lower():
                return k
    for k in keys:
        if parse_date(record.get(k)):
            return k
    return None

def process_file(file_bytes: bytes) -> list[dict]:
    """
    Extract records from a file (PDF, Excel, CSV, or plain text).
    Each record has top-level keys: title, status, details, due_date.
    """
    text = extract_text_from_file(file_bytes)
    records = []

    parsed = parse_tabular(text)
    if parsed:
        for rec in parsed:
            title_key = guess_title_key(rec)
            due_key = guess_due_date_key(rec)
            title = str(rec.get(title_key, '')) or 'Unknown'
            due_str = rec.get(due_key) if due_key else None
            due_date = parse_date(due_str) if due_str else None
            details = {k: v for k, v in rec.items() if k != title_key and k != due_key}
            records.append({
                'title': title,
                'status': compute_status(due_date),
                'details': details,
                'due_date': due_date.isoformat() if due_date else None
            })
    else:
        # Try LLM extraction if key is available
        if os.environ.get("DEEPSEEK_API_KEY"):
            try:
                from openai import OpenAI
                client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
                prompt = (
                    "Extract records from the following text. Return a JSON list of objects. "
                    "Each object must have keys: title, status, details, due_date. "
                    "Status must be one of: compliant:good, at_risk:warning, non_compliant:critical, incomplete:info. "
                    "due_date is ISO-8601 string or null. Title is the primary entity (driver name, etc.). "
                    "details is a dict of extra fields.\n\nText:\n"
                ) + text[:4000]
                response = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0
                )
                content = response.choices[0].message.content
                import json
                parsed_llm = json.loads(content)
                if isinstance(parsed_llm, list):
                    for item in parsed_llm:
                        if isinstance(item, dict):
                            item.setdefault('title', 'Unknown')
                            item.setdefault('status', 'incomplete:info')
                            item.setdefault('details', {})
                            item.setdefault('due_date', None)
                    return parsed_llm
            except Exception:
                pass

        # Fallback plain text: one record per non-empty line
        non_empty_lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in non_empty_lines:
            parts = line.split(None, 1)
            title = parts[0] if parts else 'Unknown'
            detail_text = parts[1] if len(parts) > 1 else ''
            records.append({
                'title': title,
                'status': 'incomplete:info',
                'details': {'text': detail_text},
                'due_date': None
            })

    return records
