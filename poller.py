import os
import time
import json
import traceback
import datetime
import requests
import processor

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_KEY = os.environ['SUPABASE_SERVICE_KEY']
PRODUCT_ID = os.environ['PRODUCT_ID']
ANTHROPIC_API_KEY = os.environ['ANTHROPIC_API_KEY']

REST_URL = f"{SUPABASE_URL}/rest/v1"
SB_HEADERS = {
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "apikey": SUPABASE_SERVICE_KEY,
}
NOTIF_URL = "https://njyvnmczoydsaewvfhyq.supabase.co/rest/v1/notifications"

def download_file(bucket, file_path):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY})
    resp.raise_for_status()
    return resp.content

def upload_file(bucket, path, content, content_type="application/octet-stream"):
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    resp = requests.post(
        url,
        data=content,
        headers={
            **SB_HEADERS,
            "Content-Type": content_type,
            "x-upsert": "true",
        },
    )
    resp.raise_for_status()
    return url

def send_notification(customer_id, title, body, notification_type):
    try:
        requests.post(
            NOTIF_URL,
            headers={**SB_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={
                "product_id": PRODUCT_ID,
                "customer_id": customer_id,
                "title": title,
                "body": body,
                "type": notification_type,
                "read": False,
            },
            timeout=10,
        )
    except Exception:
        traceback.print_exc()

def update_job(job_id, **fields):
    resp = requests.patch(
        f"{REST_URL}/jobs?id=eq.{job_id}",
        headers={**SB_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"},
        json=fields,
    )
    resp.raise_for_status()

def poll():
    while True:
        try:
            jobs_resp = requests.get(
                f"{REST_URL}/jobs",
                headers={**SB_HEADERS, "Content-Type": "application/json"},
                params={
                    "status": "eq.pending",
                    "job_type": "eq.process_upload",
                    "product_id": f"eq.{PRODUCT_ID}",
                    "select": "*",
                },
            )
            jobs_resp.raise_for_status()
            jobs = jobs_resp.json()
            print(f"Found {len(jobs)} pending jobs")
        except Exception:
            traceback.print_exc()
            time.sleep(60)
            continue

        for job in jobs:
            job_id = job.get("id")
            customer_id = job.get("customer_id")
            input_file_path = job.get("input_file_path")
            print(f"Processing job {job_id}")

            try:
                file_bytes = download_file("uploads", input_file_path)
                output = processor.process_file(file_bytes)
                if isinstance(output, list):
                    records = output
                elif isinstance(output, dict):
                    records = output.get("records", [])
                else:
                    records = []

                for r in records:
                    requests.post(
                        f"{REST_URL}/records",
                        headers={**SB_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"},
                        json={
                            "product_id": PRODUCT_ID,
                            "customer_id": customer_id,
                            "title": r.get("title"),
                            "status": r.get("status"),
                            "details": r.get("details", {}),
                            "source_file_path": job["input_file_path"],
                            "due_date": r.get("due_date"),
                        },
                    ).raise_for_status()

                result_payload = {
                    "product_id": PRODUCT_ID,
                    "customer_id": customer_id,
                    "job_id": job_id,
                    "records": records,
                    "created_at": datetime.datetime.utcnow().isoformat() + "Z",
                }
                result_path = f"{PRODUCT_ID}/{job_id}.json"
                upload_file("results", result_path, json.dumps(result_payload, default=str).encode(), "application/json")

                update_job(
                    job_id,
                    status="completed",
                    output_file_path=result_path,
                    result_summary=f"Processed {len(records)} records",
                    completed_at=datetime.datetime.utcnow().isoformat() + "Z",
                )
                send_notification(customer_id, "Processing complete", "Your upload has been processed successfully.", "success")
                print(f"Job {job_id} completed")

            except Exception as e:
                traceback.print_exc()
                try:
                    update_job(
                        job_id,
                        status="failed",
                        result_summary=str(e),
                        completed_at=datetime.datetime.utcnow().isoformat() + "Z",
                    )
                except Exception:
                    traceback.print_exc()
                send_notification(customer_id, "Processing failed", "There was an error processing your upload.", "error")
                print(f"Job {job_id} failed")

        time.sleep(60)

if __name__ == "__main__":
    print("Poller started")
    poll()
