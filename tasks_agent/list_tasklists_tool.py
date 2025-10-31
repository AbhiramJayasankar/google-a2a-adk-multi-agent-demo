import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Tasks API scope for full access
SCOPES = ["https://www.googleapis.com/auth/tasks"]
FIXED_PORT = 8080

def _get_credentials():
    """Helper function to get user credentials for Tasks API."""
    creds = None
    if os.path.exists("token_tasks.json"):
        try:
            creds = Credentials.from_authorized_user_file("token_tasks.json", SCOPES)
        except Exception as e:
            print(f"Error loading token_tasks.json: {e}. Will re-authenticate.")
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

        with open("token_tasks.json", "w") as token:
            token.write(creds.to_json())
    return creds

def list_tasklists() -> dict:
    """
    Lists all task lists for the user.

    Returns:
        dict: Contains either a list of task lists or an error status.
        {
            "count": int,
            "tasklists": [
                {
                    "id": str,
                    "title": str,
                    "updated": str
                }
            ]
        }
    """
    try:
        creds = _get_credentials()
        service = build("tasks", "v1", credentials=creds)

        # Fetch all task lists
        results = service.tasklists().list().execute()
        tasklists = results.get('items', [])

        if not tasklists:
            return {
                "count": 0,
                "tasklists": [],
                "message": "No task lists found."
            }

        formatted_lists = []
        for tasklist in tasklists:
            formatted_lists.append({
                "id": tasklist['id'],
                "title": tasklist.get('title', '(No Title)'),
                "updated": tasklist.get('updated', '')
            })

        return {
            "count": len(formatted_lists),
            "tasklists": formatted_lists
        }

    except HttpError as error:
        return {
            "status": "error",
            "message": f"An HTTP error occurred: {error}",
            "tasklists": []
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}",
            "tasklists": []
        }
