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
from agent_executor import TasksAgentExecutor
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
    port = 10004
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
                id="tasks_list_tasks",
                name="List Tasks",
                description="Shows tasks from a selected list, including status, due dates, and notes.",
                tags=["tasks", "list", "overview"],
                examples=["Show my tasks due today.", "List completed items in the default list."],
            ),
            AgentSkill(
                id="tasks_create_task",
                name="Create Task",
                description="Adds a new task with optional notes, due date, or parent task.",
                tags=["tasks", "create", "plan"],
                examples=["Add a task to call the dentist tomorrow.", "Create a subtask to send the report."],
            ),
            AgentSkill(
                id="tasks_update_task",
                name="Update Task",
                description="Modifies an existing task's title, notes, due date, or status.",
                tags=["tasks", "update", "edit"],
                examples=["Change the due date for task 123.", "Add notes to the grocery list task."],
            ),
            AgentSkill(
                id="tasks_complete_task",
                name="Complete Task",
                description="Marks a task as completed and records the completion time.",
                tags=["tasks", "complete", "done"],
                examples=["Mark task 456 as finished.", "Complete the task to submit expenses."],
            ),
            AgentSkill(
                id="tasks_delete_task",
                name="Delete Task",
                description="Removes a task permanently after confirming with the user.",
                tags=["tasks", "delete", "cleanup"],
                examples=["Delete the cancelled trip task.", "Remove task 789 from my list."],
            ),
            AgentSkill(
                id="tasks_list_tasklists",
                name="List Task Lists",
                description="Displays all available Google Task lists to help switch context.",
                tags=["tasks", "lists", "manage"],
                examples=["Show all my task lists.", "Which lists do I have besides the default?"],
            ),
        ]
        agent_card = AgentCard(
            name="Tasks Agent",
            description="An agent that manages Google Tasks and task lists.",
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
        agent_executor = TasksAgentExecutor(runner)

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
