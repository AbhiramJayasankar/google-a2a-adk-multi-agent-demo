import os
from datetime import datetime, timedelta
from typing import Optional
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

def list_events(max_results: int = 10, days_ahead: int = 7, calendar_id: str = "primary") -> dict:
    """
    Lists upcoming events from the user's calendar.

    Args:
        max_results (int): Maximum number of events to return. Defaults to 10.
        days_ahead (int): Number of days ahead to fetch events. Defaults to 7 (one week).
        calendar_id (str): Calendar ID to fetch events from. Defaults to "primary".

    Returns:
        dict: Contains either a list of events or an error status.
        {
            "count": int,
            "events": [
                {
                    "id": str,
                    "summary": str,
                    "start": str,
                    "end": str,
                    "location": str (optional),
                    "description": str (optional),
                    "attendees": list (optional),
                    "status": str,
                    "html_link": str
                }
            ]
        }
    """
    try:
        creds = _get_credentials()
        service = build("calendar", "v3", credentials=creds)

        # Get current time and time limit
        now = datetime.utcnow()
        time_max = now + timedelta(days=days_ahead)

        # Format as RFC3339 timestamp
        time_min = now.isoformat() + 'Z'
        time_max_str = time_max.isoformat() + 'Z'

        # Fetch events
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max_str,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return {
                "count": 0,
                "events": [],
                "message": f"No upcoming events found in the next {days_ahead} days."
            }

        formatted_events = []
        for event in events:
            # Handle both date and dateTime formats
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))

            formatted_event = {
                "id": event['id'],
                "summary": event.get('summary', '(No Title)'),
                "start": start,
                "end": end,
                "status": event.get('status', 'confirmed'),
                "html_link": event.get('htmlLink', '')
            }

            # Add optional fields if present
            if 'location' in event:
                formatted_event['location'] = event['location']
            if 'description' in event:
                formatted_event['description'] = event['description']
            if 'attendees' in event:
                formatted_event['attendees'] = [
                    {
                        'email': attendee.get('email'),
                        'responseStatus': attendee.get('responseStatus', 'needsAction')
                    }
                    for attendee in event['attendees']
                ]

            formatted_events.append(formatted_event)

        return {
            "count": len(formatted_events),
            "events": formatted_events,
            "time_range": f"Next {days_ahead} days from {now.strftime('%Y-%m-%d')}"
        }

    except HttpError as error:
        return {
            "status": "error",
            "message": f"An HTTP error occurred: {error}",
            "events": []
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}",
            "events": []
        }
