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

def complete_task(task_id: str, tasklist_id: str = "@default") -> dict:
    """
    Marks a task as completed.

    Args:
        task_id (str): The ID of the task to complete (required).
        tasklist_id (str): Task list ID containing the task. Defaults to "@default".

    Returns:
        dict: Contains completion status and details.
        Success:
        {
            "status": "success",
            "message": "Task marked as completed",
            "task_id": str,
            "title": str,
            "completed": str,  # Timestamp when completed
            "task_status": str
        }
        Error:
        {
            "status": "error",
            "message": str,
            "details": str,
            "task_id": str
        }
    """
    try:
        creds = _get_credentials()
        service = build("tasks", "v1", credentials=creds)

        # First, retrieve the existing task
        task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()

        # Build update body with only writable fields
        update_body = {
            'id': task['id'],
            'title': task.get('title', ''),
            'status': 'completed'
        }

        # Preserve optional fields if they exist
        if 'notes' in task:
            update_body['notes'] = task['notes']
        if 'due' in task:
            update_body['due'] = task['due']

        # Update the task
        updated_task = service.tasks().update(
            tasklist=tasklist_id,
            task=task_id,
            body=update_body
        ).execute()

        return {
            "status": "success",
            "message": "Task marked as completed",
            "task_id": updated_task['id'],
            "title": updated_task.get('title'),
            "completed": updated_task.get('completed', ''),
            "task_status": updated_task.get('status', 'completed')
        }

    except HttpError as error:
        if error.resp.status == 404:
            return {
                "status": "error",
                "message": "Task not found",
                "details": f"No task with ID '{task_id}' exists in the task list",
                "task_id": task_id
            }
        else:
            return {
                "status": "error",
                "message": "Failed to complete task",
                "details": str(error),
                "task_id": task_id
            }
    except Exception as e:
        return {
            "status": "error",
            "message": "An unexpected error occurred",
            "details": str(e),
            "task_id": task_id
        }
