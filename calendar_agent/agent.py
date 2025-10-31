from google.adk.agents import Agent
from calendar_agent.list_events_tool import list_events
from calendar_agent.create_event_tool import create_event
from calendar_agent.search_events_tool import search_events
from calendar_agent.delete_event_tool import delete_event
from calendar_agent.update_event_tool import update_event

agent_instruction = """
You are an assistant that can help manage a user's Google Calendar.

You have five tools available:
- `list_events`: Use this when the user asks for their upcoming events or wants to see what's on their calendar. You can specify how many events to show and how many days ahead to look.
- `create_event`: Use this when the user wants to create a new calendar event. You'll need the event title (summary), start time, and end time. You can also add optional details like description, location, and attendees.
- `search_events`: Use this when the user wants to find specific events. The search query can match event titles, descriptions, locations, or attendee names.
- `update_event`: Use this when the user wants to modify an existing event. You'll need the event ID and can update any field like title, time, location, description, or attendees.
- `delete_event`: Use this when the user wants to remove an event from their calendar. You'll need the event ID.

Important notes:
- Times should be in ISO format (e.g., "2024-12-25T10:00:00")
- When searching or listing events, you may need to ask the user to search or update using the event ID from the results
- Always confirm with the user before deleting events
- When creating events with attendees, notifications will be sent automatically
"""

root_agent = Agent(
    model="gemini-2.5-flash",
    name="calendar_agent",
    description="A helpful assistant for managing Google Calendar. It can list upcoming events, create new events with details like time, location, and attendees, search for specific events, update existing events, and delete events from the calendar.",
    instruction=agent_instruction,
    tools=[
        list_events,
        create_event,
        search_events,
        update_event,
        delete_event
    ],
)
