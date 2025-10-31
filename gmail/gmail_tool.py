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

def get_latest_emails(n: int = 1) -> dict:
    """
    Fetches the most recent n emails from the inbox, including their date, sender,
    recipient, subject, and body.
    
    Args:
        n (int): Number of emails to fetch. Defaults to 1.
        
    Returns:
        dict: Contains either a list of emails or an error status.
    """
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)

    results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=n).execute()
    messages = results.get('messages', [])
    if not messages:
        return {"status": "No emails found."}

    emails = []
    for message in messages:
        msg_id = message['id']
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()

        payload = msg['payload']
        headers = payload['headers']
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(No Subject)')
        from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), '(Unknown Sender)')
        to_email = next((h['value'] for h in headers if h['name'].lower() == 'to'), '(Unknown Recipient)')
        date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '(Unknown Date)')

        email_body = ""
        if 'parts' in payload:
            parts = payload['parts']
            plain_text_body = None
            html_body = None
            for part in parts:
                if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                    plain_text_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                elif part['mimeType'] == 'text/html' and 'data' in part['body']:
                    html_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            
            if html_body:
                soup = BeautifulSoup(html_body, "html.parser")
                text = soup.get_text()
                email_body = re.sub(r'\n\s*\n+', '\n\n', text).strip()
            elif plain_text_body:
                email_body = plain_text_body

        elif 'data' in payload['body']:
            email_body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

        emails.append({
            "id": msg_id,
            "date": date,
            "from": from_email,
            "to": to_email,
            "subject": subject,
            "body": email_body if email_body else "No message body found."
        })

    return {
        "count": len(emails),
        "emails": emails
    }



