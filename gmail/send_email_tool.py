import os
import base64
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Using gmail.modify scope to allow sending emails
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

def send_email(to: str, subject: str, body: str, cc: Optional[str] = None, bcc: Optional[str] = None) -> dict:
    """
    Sends an email from the user's Gmail account.

    Args:
        to: Recipient email address (required)
        subject: Email subject line (required)
        body: Email body content (required)
        cc: Carbon copy recipients (optional, comma-separated)
        bcc: Blind carbon copy recipients (optional, comma-separated)

    Returns:
        dict: Status of the email send operation with message ID if successful

    Example:
        send_email(
            to="recipient@example.com",
            subject="Hello",
            body="This is a test email"
        )
    """
    try:
        creds = _get_credentials()
        service = build("gmail", "v1", credentials=creds)

        # Create the email message
        message = MIMEMultipart()
        message['To'] = to
        message['Subject'] = subject

        if cc:
            message['Cc'] = cc
        if bcc:
            message['Bcc'] = bcc

        # Attach the body as plain text
        message.attach(MIMEText(body, 'plain'))

        # Encode the message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        # Send the message
        send_result = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()

        return {
            "status": "success",
            "message": "Email sent successfully",
            "message_id": send_result['id'],
            "thread_id": send_result['threadId'],
            "to": to,
            "subject": subject
        }

    except HttpError as error:
        return {
            "status": "error",
            "message": f"An error occurred: {error}",
            "details": str(error)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to send email: {str(e)}"
        }
