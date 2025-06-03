import os
import requests
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# FileMaker configuration from environment variables
FM_USERNAME = os.getenv('FM_USERNAME')
FM_PASSWORD = os.getenv('FM_PASSWORD')
FM_HOST = os.getenv('FM_HOST')
FM_DATABASE = os.getenv('FM_DATABASE')

if not all([FM_USERNAME, FM_PASSWORD, FM_HOST, FM_DATABASE]):
    raise ValueError("Missing required FileMaker environment variables")

# FileMaker API endpoints
FM_BASE_URL = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}"
FM_AUTH_URL = f"{FM_BASE_URL}/sessions"
FM_SCRIPT_URL = f"{FM_BASE_URL}/scripts"

class FileMakerClient:
    def __init__(self):
        self.token = None
        self.authenticate()

    def authenticate(self):
        """Authenticate with FileMaker and store the token"""
        response = requests.post(
            FM_AUTH_URL,
            auth=(FM_USERNAME, FM_PASSWORD)
        )
        response.raise_for_status()
        self.token = response.json()['response']['token']

    def get_tools(self) -> Dict[str, Any]:
        """Fetch tool list from FileMaker"""
        response = requests.post(
            f"{FM_SCRIPT_URL}/GetToolList",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        response.raise_for_status()
        return response.json()['response']

    def run_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool through FileMaker"""
        payload = {
            "tool": tool_name,
            "params": params
        }
        response = requests.post(
            f"{FM_SCRIPT_URL}/RunTool",
            headers={"Authorization": f"Bearer {self.token}"},
            json=payload
        )
        response.raise_for_status()
        return response.json()['response']

# Create FileMaker client
fm_client = FileMakerClient()

# Create an MCP server
mcp = FastMCP("FileMaker Tool Proxy")

# Fetch tools from FileMaker and register them dynamically
tools = fm_client.get_tools()
for tool in tools:
    @mcp.tool()
    def tool_wrapper(**kwargs):
        """Dynamic tool wrapper that forwards calls to FileMaker"""
        return fm_client.run_tool(tool['name'], kwargs)

    # Set the tool metadata
    tool_wrapper.__name__ = tool['name']
    tool_wrapper.__doc__ = tool['description']

# Run the server
if __name__ == "__main__":
    mcp.run()
