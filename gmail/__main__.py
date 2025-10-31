import logging
import os

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from agent import create_agent
from agent_executor import GmailAgentExecutor
from dotenv import load_dotenv
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Exception for missing API key."""

    pass


def main():
    """Starts the agent server."""
    host = "localhost"
    port = 10002
    try:
        # Check for API key only if Vertex AI is not configured
        if not os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            if not os.getenv("GOOGLE_API_KEY"):
                raise MissingAPIKeyError(
                    "GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE."
                )

        capabilities = AgentCapabilities(streaming=True)
        skills = [
            AgentSkill(
                id="gmail_get_latest",
                name="Get Latest Emails",
                description="Retrieves the most recent emails with sender, subject, and body content.",
                tags=["email", "inbox", "read"],
                examples=["Show me my newest email.", "Fetch the last two emails I received."],
            ),
            AgentSkill(
                id="gmail_search",
                name="Search Emails",
                description="Finds emails matching a keyword, sender, or subject query.",
                tags=["email", "search", "filter"],
                examples=["Look for emails from the HR team.", "Find receipts about my subscription."],
            ),
            AgentSkill(
                id="gmail_details",
                name="Email Details",
                description="Displays full metadata, body text, and attachment info for a specific email ID.",
                tags=["email", "inspect", "details"],
                examples=["Give me the full details of message ID 123.", "Show headers for the email with ID ABC."],
            ),
            AgentSkill(
                id="gmail_download_attachments",
                name="Download Email Attachments",
                description="Downloads every attachment from an email and serves local download links.",
                tags=["email", "attachments", "download"],
                examples=["Download the files from email ID 456.", "Get attachments from the message Elaine sent."],
            ),
            AgentSkill(
                id="gmail_send",
                name="Send Email",
                description="Composes and sends a new email with optional CC or BCC recipients.",
                tags=["email", "compose", "send"],
                examples=["Email Taylor confirming the meeting tomorrow.", "Send a thank-you note to info@example.com."],
            ),
        ]
        agent_card = AgentCard(
            name="Gmail Agent",
            description="An agent that can use Gmail",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=["text/plain"],
            defaultOutputModes=["text/plain"],
            capabilities=capabilities,
            skills=skills,
        )

        adk_agent = create_agent()
        runner = Runner(
            app_name=agent_card.name,
            agent=adk_agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
        agent_executor = GmailAgentExecutor(runner)

        request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=InMemoryTaskStore(),
        )
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        uvicorn.run(server.build(), host=host, port=port)
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)


if __name__ == "__main__":
    main()
