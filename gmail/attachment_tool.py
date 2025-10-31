import os
import base64
import threading
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler
from io import BytesIO
from urllib.parse import quote
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Using a more permissive scope to allow for searching and other actions
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
FIXED_PORT = 8080
FILE_SERVER_PORT = 8000

# Global variables to track the file server
_file_server = None
_file_server_thread = None
_download_path = None

def _get_credentials():
    """Helper function to get user credentials."""
    creds = None
    if os.path.exists("token.json"):
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        except Exception as e:
            print(f"Error loading token.json: {e}. Will re-authenticate.")
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

        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

def _is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def _start_file_server(download_path: str):
    """Start a simple HTTP server to serve downloaded files (singleton)."""
    global _file_server, _file_server_thread, _download_path, FILE_SERVER_PORT

    # If server is already running and serving the same path, return existing server info
    if _file_server and _file_server_thread and _file_server_thread.is_alive() and _download_path == download_path:
        return {"server": _file_server, "port": FILE_SERVER_PORT}

    # Find an available port
    port = FILE_SERVER_PORT
    max_port = FILE_SERVER_PORT + 10

    while _is_port_in_use(port) and port < max_port:
        port += 1

    # If all ports are in use, raise an error
    if port >= max_port:
        raise RuntimeError(f"Could not find available port between {FILE_SERVER_PORT} and {max_port}")

    class FileHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=download_path, **kwargs)

        def log_message(self, format_string, *args):
            # Suppress server logs to keep console clean
            pass

    try:
        _file_server = HTTPServer(('localhost', port), FileHandler)
        _file_server_thread = threading.Thread(target=_file_server.serve_forever, daemon=True)
        _file_server_thread.start()
        _download_path = download_path

        # Update the global port variable for URL generation
        FILE_SERVER_PORT = port

        return {"server": _file_server, "port": port}
    except Exception as e:
        raise RuntimeError(f"Could not start file server on port {port}: {e}")

def download_email_attachments(email_id: str) -> dict:
    """
    Downloads all attachments from an email and returns localhost download links.
    Automatically starts a file server if not already running.
    
    Args:
        email_id (str): The Gmail message ID
        
    Returns:
        dict: Contains download links and file information
    """
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)
    
    try:
        # Create downloads directory
        download_path = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_path, exist_ok=True)

        # Start file server automatically
        server_info = _start_file_server(download_path)
        server = server_info["server"]
        server_port = server_info["port"]

        # Get the email message
        msg = service.users().messages().get(userId='me', id=email_id).execute()
        
        # Extract attachments
        attachments = []
        def extract_attachments_recursive(payload):
            # Check if this part is an attachment (at any level)
            if payload.get('filename') and payload['body'].get('attachmentId'):
                attachments.append({
                    'attachment_id': payload['body']['attachmentId'],
                    'filename': payload['filename'],
                    'mime_type': payload['mimeType'],
                    'size': payload['body'].get('size', 0)
                })

            # Then recurse into sub-parts if they exist
            if 'parts' in payload:
                for part in payload['parts']:
                    extract_attachments_recursive(part)

        extract_attachments_recursive(msg['payload'])
        
        if not attachments:
            return {
                "status": "No attachments found in this email.",
                "file_server_running": server is not None,
                "server_info": f"File server running at http://localhost:{server_port}" if server else "File server not running"
            }
        
        downloaded_files = []
        failed_downloads = []
        
        # Download each attachment
        for attachment in attachments:
            try:
                # Get the attachment data
                attachment_data = service.users().messages().attachments().get(
                    userId='me', 
                    messageId=email_id, 
                    id=attachment['attachment_id']
                ).execute()
                
                # Decode the attachment data
                file_data = base64.urlsafe_b64decode(attachment_data['data'])
                
                # Create unique filename if file exists
                filename = attachment['filename']
                file_path = os.path.join(download_path, filename)
                counter = 1
                original_filename = filename
                while os.path.exists(file_path):
                    name, ext = os.path.splitext(original_filename)
                    filename = f"{name}_{counter}{ext}"
                    file_path = os.path.join(download_path, filename)
                    counter += 1
                
                # Write the file
                with open(file_path, 'wb') as f:
                    f.write(file_data)

                # Create download link using the actual server port with URL encoding for spaces
                download_link = f"http://localhost:{server_port}/{quote(filename)}"
                
                downloaded_files.append({
                    "filename": filename,
                    "original_filename": attachment['filename'],
                    "download_link": download_link,
                    "file_size": len(file_data),
                    "mime_type": attachment['mime_type']
                })
                
            except Exception as e:
                failed_downloads.append({
                    "filename": attachment['filename'],
                    "error": str(e)
                })
        
        result = {
            "email_id": email_id,
            "total_attachments": len(attachments),
            "successful_downloads": len(downloaded_files),
            "failed_downloads": len(failed_downloads),
            "download_links": downloaded_files,
            "failed_files": failed_downloads,
            "file_server_running": server is not None,
            "server_info": f"File server running at http://localhost:{server_port}" if server else "File server not running"
        }

        return result
        
    except HttpError as error:
        return {"error": f"Gmail API error: {error}"}
    except Exception as error:
        return {"error": f"Unexpected error: {error}"}
