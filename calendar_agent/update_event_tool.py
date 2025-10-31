import os
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

def update_event(
    event_id: str,
    summary: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    timezone: Optional[str] = None,
    calendar_id: str = "primary"
) -> dict:
    """
    Updates an existing event in the user's calendar.

    Args:
        event_id (str): The ID of the event to update (required).
        summary (str, optional): New title of the event.
        start_datetime (str, optional): New start time in ISO format (e.g., "2024-12-25T10:00:00").
        end_datetime (str, optional): New end time in ISO format (e.g., "2024-12-25T11:00:00").
        description (str, optional): New description of the event.
        location (str, optional): New location of the event.
        attendees (List[str], optional): New list of attendee email addresses.
        timezone (str, optional): New timezone for the event.
        calendar_id (str): Calendar ID containing the event. Defaults to "primary".

    Returns:
        dict: Contains update status and details.
        Success:
        {
            "status": "success",
            "message": "Event updated successfully",
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
            "details": str,
            "event_id": str
        }
    """
    try:
        creds = _get_credentials()
        service = build("calendar", "v3", credentials=creds)

        # First, retrieve the existing event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        # Update only the fields that were provided
        if summary is not None:
            event['summary'] = summary

        if start_datetime is not None:
            if 'dateTime' in event['start']:
                event['start']['dateTime'] = start_datetime
                if timezone:
                    event['start']['timeZone'] = timezone
            else:
                # Convert all-day event to timed event
                event['start'] = {
                    'dateTime': start_datetime,
                    'timeZone': timezone if timezone else 'UTC'
                }

        if end_datetime is not None:
            if 'dateTime' in event['end']:
                event['end']['dateTime'] = end_datetime
                if timezone:
                    event['end']['timeZone'] = timezone
            else:
                # Convert all-day event to timed event
                event['end'] = {
                    'dateTime': end_datetime,
                    'timeZone': timezone if timezone else 'UTC'
                }

        if description is not None:
            event['description'] = description

        if location is not None:
            event['location'] = location

        if attendees is not None:
            event['attendees'] = [{'email': email} for email in attendees]

        # Update the event
        updated_event = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event,
            sendUpdates='all' if 'attendees' in event else 'none'
        ).execute()

        return {
            "status": "success",
            "message": "Event updated successfully",
            "event_id": updated_event['id'],
            "summary": updated_event.get('summary'),
            "start": updated_event['start'].get('dateTime', updated_event['start'].get('date')),
            "end": updated_event['end'].get('dateTime', updated_event['end'].get('date')),
            "html_link": updated_event.get('htmlLink', ''),
            "location": updated_event.get('location', 'No location specified')
        }

    except HttpError as error:
        if error.resp.status == 404:
            return {
                "status": "error",
                "message": "Event not found",
                "details": f"No event with ID '{event_id}' exists in the calendar",
                "event_id": event_id
            }
        else:
            return {
                "status": "error",
                "message": "Failed to update event",
                "details": str(error),
                "event_id": event_id
            }
    except Exception as e:
        return {
            "status": "error",
            "message": "An unexpected error occurred",
            "details": str(e),
            "event_id": event_id
        }
