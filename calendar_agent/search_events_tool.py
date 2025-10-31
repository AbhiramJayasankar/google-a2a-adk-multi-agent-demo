import os
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

def search_events(
    query: str,
    max_results: int = 10,
    calendar_id: str = "primary"
) -> dict:
    """
    Searches for events in the user's calendar based on a text query.

    Args:
        query (str): Search query to find events (searches in summary, description, location, attendees).
        max_results (int): Maximum number of events to return. Defaults to 10.
        calendar_id (str): Calendar ID to search in. Defaults to "primary".

    Returns:
        dict: Contains either a list of matching events or an error status.
        {
            "count": int,
            "query": str,
            "events": [
                {
                    "id": str,
                    "summary": str,
                    "start": str,
                    "end": str,
                    "location": str (optional),
                    "description": str (optional),
                    "status": str,
                    "html_link": str
                }
            ]
        }
    """
    try:
        creds = _get_credentials()
        service = build("calendar", "v3", credentials=creds)

        # Search for events using the text query
        events_result = service.events().list(
            calendarId=calendar_id,
            q=query,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return {
                "count": 0,
                "query": query,
                "events": [],
                "message": f"No events found matching '{query}'."
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

            formatted_events.append(formatted_event)

        return {
            "count": len(formatted_events),
            "query": query,
            "events": formatted_events
        }

    except HttpError as error:
        return {
            "status": "error",
            "message": f"An HTTP error occurred: {error}",
            "query": query,
            "events": []
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}",
            "query": query,
            "events": []
        }
