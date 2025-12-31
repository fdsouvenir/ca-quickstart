"""
Cloud Function: sync-drive-to-gcs

Syncs PMIX PDFs from a shared Google Drive folder to Cloud Storage.
Triggered via HTTP webhook from external app.

Environment variables:
- DRIVE_FOLDER_ID: Google Drive folder ID containing PMIX PDFs
- BUCKET_NAME: GCS bucket name (default: fdsanalytics-pmix-uploads)
- PROJECT_ID: GCP project ID (default: fdsanalytics)
- API_KEY: Secret key for authentication (from Secret Manager)
"""

import os
import re
import functions_framework
from google.cloud import storage, bigquery
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.auth
import io


# Configuration from environment
DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', '1MPXgywD-TvvsB1bFVDQ3CocujcF8ucia')
BUCKET_NAME = os.environ.get('BUCKET_NAME', 'fdsanalytics-pmix-uploads')
PROJECT_ID = os.environ.get('PROJECT_ID', 'fdsanalytics')

# PDF filename pattern: pmix-senso-YYYY-MM-DD.pdf
FILENAME_PATTERN = re.compile(r'^pmix-senso-(\d{4}-\d{2}-\d{2})\.pdf$')


def get_imported_dates(bq_client: bigquery.Client) -> set[str]:
    """Get dates already in the import log (success or failed)."""
    query = """
        SELECT DISTINCT report_date
        FROM `fdsanalytics.insights.pmix_import_log`
    """
    try:
        results = bq_client.query(query).result()
        return {str(row.report_date) for row in results}
    except Exception as e:
        print(f"Warning: Could not query import log: {e}")
        return set()


def list_drive_pdfs(drive_service) -> list[dict]:
    """List PDF files in the Drive folder matching our pattern."""
    pdfs = []
    page_token = None

    while True:
        response = drive_service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false",
            spaces='drive',
            fields='nextPageToken, files(id, name, modifiedTime)',
            pageToken=page_token,
            pageSize=100
        ).execute()

        for file in response.get('files', []):
            name = file['name']
            match = FILENAME_PATTERN.match(name)
            if match:
                pdfs.append({
                    'id': file['id'],
                    'name': name,
                    'date': match.group(1),
                    'modified': file['modifiedTime']
                })

        page_token = response.get('nextPageToken')
        if not page_token:
            break

    return pdfs


def download_from_drive(drive_service, file_id: str) -> bytes:
    """Download a file from Drive and return its contents."""
    request = drive_service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    buffer.seek(0)
    return buffer.read()


def upload_to_gcs(storage_client: storage.Client, blob_name: str, data: bytes):
    """Upload data to GCS bucket."""
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data, content_type='application/pdf')
    print(f"Uploaded: gs://{BUCKET_NAME}/{blob_name}")


@functions_framework.http
def sync_drive_to_gcs(request):
    """
    HTTP Cloud Function entry point.
    Syncs new PMIX PDFs from Drive to GCS.
    """
    # Validate API key
    api_key = request.headers.get('X-API-Key')
    expected_key = os.environ.get('API_KEY')

    if not expected_key:
        print("Warning: API_KEY not configured")
        return {'error': 'Server misconfigured'}, 500

    if not api_key or api_key != expected_key:
        return {'error': 'Unauthorized'}, 401

    # Initialize clients
    credentials, _ = google.auth.default()
    drive_service = build('drive', 'v3', credentials=credentials)
    storage_client = storage.Client(project=PROJECT_ID)
    bq_client = bigquery.Client(project=PROJECT_ID)

    # Get already-imported dates from import log
    imported_dates = get_imported_dates(bq_client)
    print(f"Found {len(imported_dates)} dates in import log")

    # List PDFs in Drive folder
    drive_pdfs = list_drive_pdfs(drive_service)
    print(f"Found {len(drive_pdfs)} PDFs in Drive folder")

    # Find new files (not in import log)
    new_files = [f for f in drive_pdfs if f['date'] not in imported_dates]
    print(f"Found {len(new_files)} new files to sync")

    if not new_files:
        return {'message': 'No new files to sync', 'synced': 0}

    # Download from Drive and upload to GCS
    synced = 0
    errors = []

    for file_info in new_files:
        try:
            print(f"Syncing: {file_info['name']}")

            # Download from Drive
            pdf_data = download_from_drive(drive_service, file_info['id'])

            # Upload to GCS incoming/
            blob_name = f"incoming/{file_info['name']}"
            upload_to_gcs(storage_client, blob_name, pdf_data)

            synced += 1

        except Exception as e:
            error_msg = f"Error syncing {file_info['name']}: {e}"
            print(error_msg)
            errors.append(error_msg)

    result = {
        'message': f'Synced {synced} files',
        'synced': synced,
        'errors': errors if errors else None
    }

    print(f"Sync complete: {result}")
    return result
