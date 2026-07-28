"""MCP server exposing Trello ticket access as two narrowly-scoped tools:
get_ticket (read a ticket) and post_summary (write a run summary back).

Run directly for MCP Inspector debugging:
    mcp dev app/mcp_server/server.py
"""

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from app.mcp_server.trello_client import TrelloClient, TrelloError

load_dotenv()

mcp = FastMCP("trello-ticket-server")


@mcp.tool()
async def get_ticket(ticket_id: str) -> dict:
    """Reads a ticket's title, description, and checklist from the connected
    Trello board. Returns a structured error if the ticket doesn't exist."""
    try:
        client = TrelloClient()
        return await client.get_card(ticket_id)
    except TrelloError as exc:
        return {"error": str(exc)}


@mcp.tool()
async def post_summary(ticket_id: str, summary: str) -> dict:
    """Posts a run summary as a comment onto the given ticket. Returns a
    structured error if the ticket doesn't exist or the post fails."""
    try:
        client = TrelloClient()
        return await client.add_comment(ticket_id, summary)
    except TrelloError as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    mcp.run()
