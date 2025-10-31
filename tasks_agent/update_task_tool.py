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

def update_task(
    task_id: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    due: Optional[str] = None,
    status: Optional[str] = None,
    tasklist_id: str = "@default"
) -> dict:
    """
    Updates an existing task.

    Args:
        task_id (str): The ID of the task to update (required).
        title (str, optional): New title for the task.
        notes (str, optional): New notes for the task.
        due (str, optional): New due date in RFC 3339 format (e.g., "2024-12-25T00:00:00Z").
        status (str, optional): New status ("needsAction" or "completed").
        tasklist_id (str): Task list ID containing the task. Defaults to "@default".

    Returns:
        dict: Contains update status and details.
        Success:
        {
            "status": "success",
            "message": "Task updated successfully",
            "task_id": str,
            "title": str,
            "notes": str,
            "due": str,
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
        # We need to preserve existing values for fields not being updated
        update_body = {
            'id': task['id'],
            'title': title if title is not None else task.get('title', ''),
            'status': status if status is not None else task.get('status', 'needsAction')
        }

        # Add optional fields only if they exist or are being updated
        if notes is not None:
            update_body['notes'] = notes
        elif 'notes' in task:
            update_body['notes'] = task['notes']

        if due is not None:
            update_body['due'] = due
        elif 'due' in task:
            update_body['due'] = task['due']

        # Update the task
        updated_task = service.tasks().update(
            tasklist=tasklist_id,
            task=task_id,
            body=update_body
        ).execute()

        return {
            "status": "success",
            "message": "Task updated successfully",
            "task_id": updated_task['id'],
            "title": updated_task.get('title'),
            "notes": updated_task.get('notes', 'No notes'),
            "due": updated_task.get('due', 'No due date'),
            "task_status": updated_task.get('status', 'needsAction')
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
                "message": "Failed to update task",
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
