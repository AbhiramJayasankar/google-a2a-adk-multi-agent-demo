import os
import base64
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bs4 import BeautifulSoup

# Using a more permissive scope to allow for searching and other actions
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
FIXED_PORT = 8080

def _get_credentials():
    """Helper function to get user credentials."""
    creds = None
    if os.path.exists("token.json"):
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        except Exception as e:
            print(f"Error loading token.json: {e}. Will re-authenticate.")
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                # Refresh failed, need full re-auth
                print(f"Token refresh failed: {e}")
                creds = None

        if not creds:  # Either no token or refresh failed
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(
                port=FIXED_PORT,
                access_type='offline',
                prompt='consent'
            )

        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

def get_email_details(email_id: str) -> dict:
    """
    Retrieves full details of a specific email given its ID.

    Args:
        email_id (str): The Gmail message ID

    Returns:
        dict: Contains complete email details including headers, body, labels, and attachments info
    """
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)

    try:
        # Get the email message with full format
        msg = service.users().messages().get(userId='me', id=email_id, format='full').execute()

        payload = msg['payload']
        headers = payload.get('headers', [])

        # Extract all important headers
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(No Subject)')
        from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), '(Unknown Sender)')
        to_email = next((h['value'] for h in headers if h['name'].lower() == 'to'), '(Unknown Recipient)')
        cc_email = next((h['value'] for h in headers if h['name'].lower() == 'cc'), None)
        bcc_email = next((h['value'] for h in headers if h['name'].lower() == 'bcc'), None)
        date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '(Unknown Date)')
        message_id = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), None)

        # Extract email body
        email_body_plain = ""
        email_body_html = ""

        def extract_body_recursive(payload):
            """Recursively extract body from email parts."""
            nonlocal email_body_plain, email_body_html

            # Check if this part has a body
            if 'mimeType' in payload:
                if payload['mimeType'] == 'text/plain' and 'data' in payload.get('body', {}):
                    email_body_plain = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
                elif payload['mimeType'] == 'text/html' and 'data' in payload.get('body', {}):
                    email_body_html = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

            # Recurse into parts if they exist
            if 'parts' in payload:
                for part in payload['parts']:
                    extract_body_recursive(part)

        # Extract body from payload
        extract_body_recursive(payload)

        # If we have HTML, convert it to readable text
        body_text = ""
        if email_body_html:
            soup = BeautifulSoup(email_body_html, "html.parser")
            text = soup.get_text()
            body_text = re.sub(r'\n\s*\n+', '\n\n', text).strip()
        elif email_body_plain:
            body_text = email_body_plain

        # Extract attachment information
        attachments = []
        def extract_attachments_recursive(payload):
            if payload.get('filename') and payload.get('body', {}).get('attachmentId'):
                attachments.append({
                    'filename': payload['filename'],
                    'mime_type': payload.get('mimeType', 'unknown'),
                    'size': payload.get('body', {}).get('size', 0),
                    'attachment_id': payload['body']['attachmentId']
                })

            if 'parts' in payload:
                for part in payload['parts']:
                    extract_attachments_recursive(part)

        extract_attachments_recursive(payload)

        # Get labels
        labels = msg.get('labelIds', [])

        # Get thread ID
        thread_id = msg.get('threadId', None)

        # Build the response
        email_details = {
            "id": email_id,
            "thread_id": thread_id,
            "labels": labels,
            "snippet": msg.get('snippet', ''),
            "date": date,
            "from": from_email,
            "to": to_email,
            "subject": subject,
            "body": body_text if body_text else "No message body found.",
            "size_estimate": msg.get('sizeEstimate', 0),
            "has_attachments": len(attachments) > 0,
            "attachment_count": len(attachments),
            "attachments": attachments
        }

        # Add optional fields if they exist
        if cc_email:
            email_details["cc"] = cc_email
        if bcc_email:
            email_details["bcc"] = bcc_email
        if message_id:
            email_details["message_id"] = message_id

        # Add raw HTML body if needed
        if email_body_html:
            email_details["body_html"] = email_body_html

        return email_details

    except HttpError as error:
        return {"error": f"Gmail API error: {error}"}
    except Exception as error:
        return {"error": f"Unexpected error: {error}"}
