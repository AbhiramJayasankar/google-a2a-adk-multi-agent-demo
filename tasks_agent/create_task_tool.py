import os
from typing import Optional
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

def create_task(
    title: str,
    notes: Optional[str] = None,
    due: Optional[str] = None,
    parent: Optional[str] = None,
    tasklist_id: str = "@default"
) -> dict:
    """
    Creates a new task in a task list.

    Args:
        title (str): Title of the task (required).
        notes (str, optional): Notes or description for the task.
        due (str, optional): Due date in RFC 3339 format (e.g., "2024-12-25T00:00:00Z").
        parent (str, optional): Parent task ID if creating a subtask.
        tasklist_id (str): Task list ID to create task in. Defaults to "@default".

    Returns:
        dict: Contains task creation status and details.
        Success:
        {
            "status": "success",
            "message": "Task created successfully",
            "task_id": str,
            "title": str,
            "notes": str (optional),
            "due": str (optional),
            "tasklist_id": str
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
        service = build("tasks", "v1", credentials=creds)

        # Build task body
        task = {
            'title': title
        }

        # Add optional fields
        if notes:
            task['notes'] = notes
        if due:
            task['due'] = due

        # Create the task
        params = {'tasklist': tasklist_id, 'body': task}

        if parent:
            params['parent'] = parent

        created_task = service.tasks().insert(**params).execute()

        return {
            "status": "success",
            "message": "Task created successfully",
            "task_id": created_task['id'],
            "title": created_task.get('title'),
            "notes": created_task.get('notes', 'No notes'),
            "due": created_task.get('due', 'No due date'),
            "tasklist_id": tasklist_id,
            "position": created_task.get('position', '')
        }

    except HttpError as error:
        return {
            "status": "error",
            "message": "Failed to create task",
            "details": str(error)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": "An unexpected error occurred",
            "details": str(e)
        }
