import processor

test_bytes = b"driver_name,license_number,license_expiration_date,medical_card_expiration_date,mvr_due_date\nJohn Doe,DL123456,2026-12-31,2026-05-15,2025-12-01"

results = processor.process_file(test_bytes)
assert isinstance(results, list)
assert len(results) > 0

for rec in results:
    assert isinstance(rec, dict)
    assert 'title' in rec and 'status' in rec and 'details' in rec and 'due_date' in rec
    print(rec)

assert results[0]['title'] == 'John Doe'
assert results[0]['due_date'] == '2026-12-31'
assert results[0]['status'] == 'compliant:good'
assert results[0]['details']['license_number'] == 'DL123456'

print("Demo passed")
exit(0)
