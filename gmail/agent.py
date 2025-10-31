from google.adk.agents import LlmAgent
from gmail_tool import get_latest_emails
from search_tool import search_emails
from attachment_tool import download_email_attachments
from send_email_tool import send_email
from email_details_tool import get_email_details

agent_instruction = """
You are an assistant that can help manage a user's Gmail inbox.

You have five tools available:
- `get_latest_email`: Use this when the user asks for their most recent email.
- `search_emails`: Use this when the user wants to find specific emails. You will need to ask them for a search query, like 'from:amazon' or 'subject:receipt'.
- `get_email_details`: Use this when the user wants complete information about a specific email given its ID. This includes full headers, body content, labels, and attachment information.
- `download_email_attachments`: Use this when the user wants to download attachments from a specific email. You'll need the email ID.
- `send_email`: Use this when the user wants to send an email. You'll need the recipient address, subject, and body. Optionally support CC and BCC.
"""


def create_agent() -> LlmAgent:
    """Constructs the ADK agent for Karley."""
    return LlmAgent(
    model="gemini-2.5-flash",
    name="email_agent",
    description="A helpful assistant for managing Gmail. It can retrieve the most recent email, perform searches using keywords, senders, or subjects to find specific messages, get full details of a specific email by ID, download all attachments from an email and return localhost download links, and send emails to recipients.",
    instruction=agent_instruction,
    tools=[
        get_latest_emails,
        search_emails,
        get_email_details,
        download_email_attachments,
        send_email
    ],
)
