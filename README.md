# FleetDocs

FleetDocs is a document-extraction backend for DOT / fleet compliance paperwork. It ingests uploaded files (driver qualification files, MVRs, medical cards, license scans, spreadsheets, and plain-text exports) and turns them into structured compliance records with a computed status and due date.

## Product Archetype

FleetDocs is a **document ingestion + compliance-status engine**. It sits behind an upload surface: a fleet manager drops a file, the processor extracts the primary entity (usually a driver), the relevant expiration/due date, and any remaining fields as details, then classifies each record into a traffic-light status.

The engine is stateless and pure: `process_file(file_bytes) -> list[dict]`. It has no database dependency, which makes it directly embeddable in a poller/worker process.

## Modules

- `processor.py` – Core extraction module. Defines `process_file(file_bytes: bytes) -> list[dict]`. Handles PDF (via `pdfplumber`), Excel (via `openpyxl`), CSV, and plain text (UTF-8 fallback). Optional LLM extraction via `deepseek-v4-flash` when `DEEPSEEK_API_KEY` is set and the input is unstructured.
- `run_demo.py` – Zero-argument demo script. Uses hardcoded CSV test data, calls `processor.process_file`, asserts the result structure, and exits 0 in under 10 seconds.
- `run_tests.py` – Basic test suite covering CSV parsing, Excel parsing, and plain-text fallback. Exits 0 on success.
- `requirements.txt` – Python dependencies (`openai`, `requests`, `pdfplumber`, `openpyxl`).

## Output Record Shape

Each extracted record is a dict with exactly these top-level keys:

- `title` – primary entity (driver name, employee, vendor, etc.).
- `status` – one of `compliant:good`, `at_risk:warning`, `non_compliant:critical`, `incomplete:info`.
- `details` – dict of all remaining fields captured from the source document.
- `due_date` – ISO-8601 date string (`YYYY-MM-DD`) or `null`.

## Status Logic

Status is derived from the due date relative to today:

| Condition | Status |
|---|---|
| No due date found | `incomplete:info` |
| Due date in the past | `non_compliant:critical` |
| Due within 30 days | `at_risk:warning` |
| Due more than 30 days out | `compliant:good` |

## Extraction Logic

1. Attempt PDF text extraction with `pdfplumber`.
2. If that yields no text, attempt Excel extraction with `openpyxl` (all sheets, values only).
3. Otherwise decode the raw bytes as UTF-8 text and fall back to CSV.
4. Detect delimiter and header with `csv.Sniffer`; if tabular, map columns to records.
5. If unstructured and `DEEPSEEK_API_KEY` is present, ask `deepseek-v4-flash` for a JSON list of records.
6. If nothing structured is found, fall back to one record per non-empty line.

Column heuristics pick the title from keys containing `driver_name`, `name`, `employee_name`, `vendor_name`, `contract_party`, `patient_name`, or `title`, and pick the due date from keys containing `expiration`, `expires`, `due_date`, `due`, `expiry`, or `expiration_date` (or the first parseable date column).

## Poller Contract

The poller (worker process) expects to call `processor.process_file(file_bytes)` with the raw bytes of a single uploaded file and receive a JSON-serializable `list[dict]` back. It then writes each record to the datastore, keyed on the parent upload.

- **Input:** raw `bytes` of one uploaded file (PDF, XLSX/XLS, CSV, or plain text).
- **Output:** `list[dict]`, each with `title`, `status`, `details`, `due_date`. The list may be empty if no records are extractable.
- **Side effects:** none. The function is pure and safe to retry.
- **Env:** optional `DEEPSEEK_API_KEY` enables LLM extraction for unstructured inputs. Without it, tabular and text fallbacks are used.

## Usage

```bash
python3 run_demo.py
python3 run_tests.py
```

Both scripts are zero-argument and exit 0 on success.
Dashboard: https://fleetdocs.vokrix.co
Vercel: fleetdocs
Railway: fleetdocs
Cloudflare: fleetdocs.vokrix.co

Billing: price_1UKSLB2c9uGCcgMS9IJHAmG5

Billing: price_1UKSLB2c9uGCcgMS9IJHAmG5
