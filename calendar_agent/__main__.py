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
from agent_executor import CalenderAgentExecutor
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
    port = 10003
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
                id="calendar_list_events",
                name="List Upcoming Events",
                description="Shows upcoming calendar events within a specified time window.",
                tags=["calendar", "events", "list"],
                examples=["What meetings do I have this week?", "List the next three events on my calendar."],
            ),
            AgentSkill(
                id="calendar_create_event",
                name="Create Event",
                description="Schedules a new calendar event with time, location, and optional attendees.",
                tags=["calendar", "events", "create"],
                examples=["Add a team sync tomorrow at 2 PM.", "Create a lunch meeting with Alex next Friday at noon."],
            ),
            AgentSkill(
                id="calendar_search_events",
                name="Search Events",
                description="Finds calendar entries that match titles, descriptions, or attendee names.",
                tags=["calendar", "events", "search"],
                examples=["Find my appointments with the dentist.", "Look up events that mention quarterly review."],
            ),
            AgentSkill(
                id="calendar_update_event",
                name="Update Event",
                description="Modifies details of an existing calendar event using its event ID.",
                tags=["calendar", "events", "update"],
                examples=["Move the project kickoff to 4 PM.", "Change the location of event ID 12345 to the main office."],
            ),
            AgentSkill(
                id="calendar_delete_event",
                name="Delete Event",
                description="Removes an event from the calendar after confirmation.",
                tags=["calendar", "events", "delete"],
                examples=["Cancel event ID abc123.", "Delete my coffee chat with Jamie on Friday."],
            ),
        ]
        agent_card = AgentCard(
            name="Calendar Agent",
            description="An agent that manages Google Calendar events",
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
        agent_executor = CalenderAgentExecutor(runner)

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
