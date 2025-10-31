import os
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

def delete_event(event_id: str, calendar_id: str = "primary") -> dict:
    """
    Deletes an event from the user's calendar.

    Args:
        event_id (str): The ID of the event to delete (required).
        calendar_id (str): Calendar ID containing the event. Defaults to "primary".

    Returns:
        dict: Contains deletion status.
        Success:
        {
            "status": "success",
            "message": "Event deleted successfully",
            "event_id": str
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

        # Delete the event
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
            sendUpdates='all'  # Send cancellation notifications to attendees
        ).execute()

        return {
            "status": "success",
            "message": "Event deleted successfully",
            "event_id": event_id
        }

    except HttpError as error:
        # Check if event was not found
        if error.resp.status == 404:
            return {
                "status": "error",
                "message": "Event not found",
                "details": f"No event with ID '{event_id}' exists in the calendar",
                "event_id": event_id
            }
        elif error.resp.status == 410:
            return {
                "status": "error",
                "message": "Event already deleted",
                "details": f"Event with ID '{event_id}' was already deleted",
                "event_id": event_id
            }
        else:
            return {
                "status": "error",
                "message": "Failed to delete event",
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
