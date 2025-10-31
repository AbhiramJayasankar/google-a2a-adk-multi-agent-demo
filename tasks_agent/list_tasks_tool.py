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

def list_tasks(tasklist_id: str = "@default", max_results: int = 100, show_completed: bool = False) -> dict:
    """
    Lists tasks from a specific task list.

    Args:
        tasklist_id (str): Task list ID to fetch tasks from. Defaults to "@default" (primary list).
        max_results (int): Maximum number of tasks to return. Defaults to 100.
        show_completed (bool): Whether to include completed tasks. Defaults to False.

    Returns:
        dict: Contains either a list of tasks or an error status.
        {
            "count": int,
            "tasklist_id": str,
            "tasks": [
                {
                    "id": str,
                    "title": str,
                    "notes": str (optional),
                    "status": str,  # "needsAction" or "completed"
                    "due": str (optional),  # RFC 3339 timestamp
                    "completed": str (optional),  # RFC 3339 timestamp
                    "updated": str,
                    "parent": str (optional),  # Parent task ID if subtask
                    "position": str,
                    "links": list (optional)  # Related links
                }
            ]
        }
    """
    try:
        creds = _get_credentials()
        service = build("tasks", "v1", credentials=creds)

        # Fetch tasks
        params = {
            'tasklist': tasklist_id,
            'maxResults': max_results
        }

        if show_completed:
            params['showCompleted'] = True
            params['showHidden'] = True

        results = service.tasks().list(**params).execute()
        tasks = results.get('items', [])

        if not tasks:
            return {
                "count": 0,
                "tasklist_id": tasklist_id,
                "tasks": [],
                "message": "No tasks found in this list."
            }

        formatted_tasks = []
        for task in tasks:
            formatted_task = {
                "id": task['id'],
                "title": task.get('title', '(No Title)'),
                "status": task.get('status', 'needsAction'),
                "updated": task.get('updated', ''),
                "position": task.get('position', '')
            }

            # Add optional fields if present
            if 'notes' in task:
                formatted_task['notes'] = task['notes']
            if 'due' in task:
                formatted_task['due'] = task['due']
            if 'completed' in task:
                formatted_task['completed'] = task['completed']
            if 'parent' in task:
                formatted_task['parent'] = task['parent']
            if 'links' in task:
                formatted_task['links'] = task['links']

            formatted_tasks.append(formatted_task)

        return {
            "count": len(formatted_tasks),
            "tasklist_id": tasklist_id,
            "tasks": formatted_tasks
        }

    except HttpError as error:
        return {
            "status": "error",
            "message": f"An HTTP error occurred: {error}",
            "tasklist_id": tasklist_id,
            "tasks": []
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}",
            "tasklist_id": tasklist_id,
            "tasks": []
        }
