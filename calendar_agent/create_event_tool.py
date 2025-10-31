import os
from datetime import datetime
from typing import Optional, List
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Calendar API scope for full access
SCOPES = ["https://www.googleapis.com/auth/calendar"]
FIXED_PORT = 8080

def _get_credentials():
    """Helper function to get user credentials for Calendar API."""
    creds = None
    if os.path.exists("token_calendar.json"):
        try:
            creds = Credentials.from_authorized_user_file("token_calendar.json", SCOPES)
        except Exception as e:
            print(f"Error loading token_calendar.json: {e}. Will re-authenticate.")
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

        with open("token_calendar.json", "w") as token:
            token.write(creds.to_json())
    return creds

def create_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    timezone: str = "UTC",
    calendar_id: str = "primary"
) -> dict:
    """
    Creates a new event in the user's calendar.

    Args:
        summary (str): Title of the event (required).
        start_datetime (str): Start time in ISO format (e.g., "2024-12-25T10:00:00") (required).
        end_datetime (str): End time in ISO format (e.g., "2024-12-25T11:00:00") (required).
        description (str, optional): Description of the event.
        location (str, optional): Location of the event.
        attendees (List[str], optional): List of attendee email addresses.
        timezone (str): Timezone for the event. Defaults to "UTC".
        calendar_id (str): Calendar ID to create event in. Defaults to "primary".

    Returns:
        dict: Contains event creation status and details.
        Success:
        {
            "status": "success",
            "message": "Event created successfully",
            "event_id": str,
            "summary": str,
            "start": str,
            "end": str,
            "html_link": str
        }
        Error:
        {
            "status": "error",
            "message": str,
            "details": str
        }
    """
    try:
        creds = _get_credentials()
        service = build("calendar", "v3", credentials=creds)

        # Build event body
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_datetime,
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_datetime,
                'timeZone': timezone,
            },
        }

        # Add optional fields
        if description:
            event['description'] = description
        if location:
            event['location'] = location
        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        # Create the event
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event,
            sendUpdates='all' if attendees else 'none'  # Send notifications if there are attendees
        ).execute()

        return {
            "status": "success",
            "message": "Event created successfully",
            "event_id": created_event['id'],
            "summary": created_event.get('summary'),
            "start": created_event['start'].get('dateTime', created_event['start'].get('date')),
            "end": created_event['end'].get('dateTime', created_event['end'].get('date')),
            "html_link": created_event.get('htmlLink', ''),
            "location": created_event.get('location', 'No location specified')
        }

    except HttpError as error:
        return {
            "status": "error",
            "message": "Failed to create event",
            "details": str(error)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": "An unexpected error occurred",
            "details": str(e)
        }
