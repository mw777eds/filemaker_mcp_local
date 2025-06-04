# FileMaker MCP Server

This project implements a Model Context Protocol (MCP) server that dynamically exposes FileMaker scripts as tools. It uses Gradio to provide a user interface for interacting with these tools.

## Setup

1.  **Clone the repository:**

    ```bash
    git clone <repository_url>
    cd filemaker_mcp_local
    ```

2.  **Create a virtual environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**

    Create a `.env` file in the project root with the following variables:

    ```env
    FM_USERNAME=your_filemaker_username
    FM_PASSWORD=your_filemaker_password
    FM_HOST=your_filemaker_host
    FM_DATABASE=your_filemaker_database
    FM_LAYOUT=your_filemaker_layout
    ```

    Replace the placeholder values with your actual FileMaker credentials and database details.

## Running the Server

1.  **Activate the virtual environment** (if not already active):

    ```bash
    source venv/bin/activate
    ```

2.  **Run the server script:**

    ```bash
    python gradio_mcp_server.py
    ```

This will start both the MCP server (listening on stdin/stdout for the MCP protocol) and a Gradio server (typically on port 7860) providing a web UI for the dynamically created tools.
