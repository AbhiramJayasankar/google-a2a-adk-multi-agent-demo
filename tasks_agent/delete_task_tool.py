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

def delete_task(task_id: str, tasklist_id: str = "@default") -> dict:
    """
    Deletes a task from a task list.

    Args:
        task_id (str): The ID of the task to delete (required).
        tasklist_id (str): Task list ID containing the task. Defaults to "@default".

    Returns:
        dict: Contains deletion status.
        Success:
        {
            "status": "success",
            "message": "Task deleted successfully",
            "task_id": str
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

        # Delete the task
        service.tasks().delete(
            tasklist=tasklist_id,
            task=task_id
        ).execute()

        return {
            "status": "success",
            "message": "Task deleted successfully",
            "task_id": task_id
        }

    except HttpError as error:
        # Check if task was not found
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
                "message": "Failed to delete task",
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
