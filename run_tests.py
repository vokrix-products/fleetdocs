import processor
import io
from openpyxl import Workbook

def test_csv():
    data = b"driver_name,license_expiration_date,license_number\nAlice,2026-01-15,DL111"
    results = processor.process_file(data)
    assert len(results) == 1
    rec = results[0]
    assert rec['title'] == 'Alice'
    assert rec['due_date'] == '2026-01-15'
    assert rec['details']['license_number'] == 'DL111'
    assert rec['status'] in ['compliant:good', 'at_risk:warning', 'non_compliant:critical', 'incomplete:info']

def test_excel():
    wb = Workbook()
    ws = wb.active
    ws.append(["driver_name", "license_expiration_date"])
    ws.append(["Bob", "2026-02-20"])
    bio = io.BytesIO()
    wb.save(bio)
    results = processor.process_file(bio.getvalue())
    assert len(results) == 1
    assert results[0]['title'] == 'Bob'
    assert results[0]['due_date'] == '2026-02-20'

def test_plain_text():
    data = b"Charlie\nSome text here"
    results = processor.process_file(data)
    assert isinstance(results, list)
    # Plain text fallback may produce at least one record
    if results:
        rec = results[0]
        assert 'title' in rec and 'status' in rec and 'details' in rec and 'due_date' in rec

test_csv()
test_excel()
test_plain_text()
print("All tests passed")
exit(0)
