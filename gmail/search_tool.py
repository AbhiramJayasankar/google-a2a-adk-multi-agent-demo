import os
import base64
import re
import time
import random
import socket
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bs4 import BeautifulSoup
import httplib2

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

def search_emails(query: str) -> dict:
    """
    Searches for emails in the user's inbox based on a query.
    The query uses the same format as the Gmail search box.
    Example query: 'from:example@email.com subject:important'
    """
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)

    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])

    if not messages:
        return {"status": "No emails found matching your query."}

    # Fetches details for the top 5 results
    email_list = []
    for msg_info in messages[:5]:
        msg = service.users().messages().get(userId='me', id=msg_info['id']).execute()
        payload = msg.get('payload', {})
        headers = payload.get('headers', [])
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(No Subject)')
        from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), '(Unknown Sender)')
        email_list.append({"id": msg_info['id'], "from": from_email, "subject": subject})

    return {"emails": email_list}