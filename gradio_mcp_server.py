import os
import requests
import gradio as gr
from dotenv import load_dotenv
import json
from typing import Any, Dict, Callable, List
import sys
import time
from mcp.server.fastmcp import FastMCP
import threading
from urllib.parse import urlencode
import inspect # Needed for inspecting generated functions later
import types # Needed for dynamic function creation if not using exec

def log_info(msg):
    print(msg, file=sys.stderr)

def log_error(msg):
    print(msg, file=sys.stderr)

log_info("Attempting to launch gradio_mcp_server.py - version check")

print("Starting gradio_mcp_server.py", file=sys.stderr)

load_dotenv()

FM_USERNAME = os.getenv('FM_USERNAME')
FM_PASSWORD = os.getenv('FM_PASSWORD')
FM_HOST = os.getenv('FM_HOST')
FM_DATABASE = os.getenv('FM_DATABASE')
FM_LAYOUT = os.getenv('FM_LAYOUT')

# Authenticate and get token
def get_fm_token():
    log_info("Attempting to get FileMaker token...")
    start_time = time.time()
    url = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}/sessions"
    try:
        response = requests.post(
            url,
            auth=(FM_USERNAME, FM_PASSWORD),
            headers={"Content-Type": "application/json"},
            json={}
        )
        response.raise_for_status()
        token = response.json()['response']['token']
        log_info(f"FileMaker token obtained successfully in {time.time() - start_time:.2f} seconds.")
        return token
    except requests.exceptions.RequestException as e:
        log_error(f"Error getting FileMaker token after {time.time() - start_time:.2f} seconds: {e}")
        raise # Re-raise the exception

# Call a FileMaker script
def call_filemaker_script(script_name, params):
    log_info(f"Attempting to call FileMaker script: {script_name}...")
    start_time = time.time()
    try:
        token = get_fm_token()
        url = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}/layouts/{FM_LAYOUT}/script/{script_name}"
        if params:
            # FileMaker expects script parameters as a single JSON string in the 'script.param' query parameter
            query_params = urlencode({'script.param': json.dumps(params)})
            url = f"{url}?{query_params}"

        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        result = response.json()['response']
        log_info(f"FileMaker script {script_name} called successfully in {time.time() - start_time:.2f} seconds.")
        if 'scriptResult' in result:
            try:
                return json.loads(result['scriptResult'])
            except Exception:
                return result['scriptResult']
        return result
    except requests.exceptions.RequestException as e:
        log_error(f"Error calling FileMaker script {script_name} after {time.time() - start_time:.2f} seconds: {e}")
        raise

# Fetch tool list from FileMaker
def get_tools_from_filemaker() -> list:
    log_info("Attempting to fetch tool list from FileMaker...")
    start_time = time.time()
    try:
        token = get_fm_token()
        url = f"https://{FM_HOST}/fmi/data/v1/databases/{FM_DATABASE}/layouts/{FM_LAYOUT}/script/GetToolList"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        result = response.json()['response']
        log_info(f"Raw FileMaker response: {json.dumps(result, indent=2)}")
        script_result = json.loads(result['scriptResult'])
        tools = script_result.get('tools', [])
        log_info(f"Tool list fetched successfully in {time.time() - start_time:.2f} seconds. Found {len(tools)} tools.")
        # Log the names of all tools found
        tool_names = [tool.get('function', {}).get('name', 'unknown') for tool in tools]
        log_info(f"Tools found: {', '.join(tool_names)}")
        return tools
    except requests.exceptions.RequestException as e:
        log_error(f"Error fetching tool list from FileMaker after {time.time() - start_time:.2f} seconds: {e}")
        raise

def create_dynamic_tool(tool_data: Dict[str, Any]) -> Callable:
    """Create a dynamic tool function from tool metadata."""
    function = tool_data['function']
    name = function['name']
    description = function.get('description', '')
    parameters = function.get('parameters', {})
    properties = parameters.get('properties', {})
    required = parameters.get('required', [])

    log_info(f"Creating tool function for {name} with parameters: {list(properties.keys())}")

    # Create function code with explicit parameters
    def create_tool_function():
        # Build the function signature - required parameters first, then optional ones
        required_params = []
        optional_params = []
        
        for param_name, param_info in properties.items():
            if param_name in required:
                required_params.append(param_name)
            else:
                optional_params.append(f"{param_name}=None")

        # Combine required and optional parameters
        param_list = required_params + optional_params
        param_str = ", ".join(param_list)

        # Create the function code
        func_code = f"""
def {name}({param_str}):
    \"\"\"
    {description}
    \"\"\"
    params = {{}}
"""
        # Add parameter collection
        for param_name in properties.keys():
            func_code += f"    if {param_name} is not None:\n"
            func_code += f"        params['{param_name}'] = {param_name}\n"

        func_code += f"""
    return call_filemaker_script("{name}", params)
"""
        # Create the function namespace
        namespace = {'call_filemaker_script': call_filemaker_script}
        
        # Execute the function code in the namespace
        exec(func_code, namespace)
        
        return namespace[name]

    # Create the actual function
    tool_function = create_tool_function()

    # Set parameter annotations
    type_mapping = {
        'string': str,
        'number': float,
        'integer': int,
        'boolean': bool,
        'object': Dict[str, Any],
        'array': List[Any]
    }

    annotations = {}
    for param_name, param_info in properties.items():
        param_type = param_info.get('type', 'string')
        python_type = type_mapping.get(param_type, Any)
        annotations[param_name] = python_type

    tool_function.__annotations__ = annotations
    log_info(f"Successfully created tool function for {name} with annotations: {annotations}")

    return tool_function

# Create MCP server
server = FastMCP("FileMaker Tools")

# Create Gradio interface components for a tool
def create_gradio_tool(tool_name: str, tool_func: Callable, tool_data: Dict[str, Any]) -> tuple[Callable, list, str, str]:
    function = tool_data['function']
    name = function['name']
    description = function.get('description', '')
    parameters = function.get('parameters', {})
    properties = parameters.get('properties', {})
    required = parameters.get('required', [])

    # Create input components based on parameters
    inputs = []
    for param_name, param_info in properties.items():
        param_type = param_info.get('type', 'string')
        param_desc = param_info.get('description', '')

        if param_type == 'string':
            inputs.append(gr.Textbox(label=f"{param_name} ({param_desc})"))
        elif param_type == 'number' or param_type == 'integer': # Handle both number and integer
            inputs.append(gr.Number(label=f"{param_name} ({param_desc})"))
        elif param_type == 'boolean':
            inputs.append(gr.Checkbox(label=f"{param_name} ({param_desc})"))
        else:
            # Default to Textbox for unhandled types
            inputs.append(gr.Textbox(label=f"{param_name} ({param_desc})"))

    # The function to be called by Gradio is the imported tool_func
    # We wrap it to ensure the return type is always string for Gradio Textbox output
    def gradio_wrapper_func(*args):
        # Map Gradio args back to keyword args based on the order of properties
        kwargs = dict(zip(properties.keys(), args))
        result = tool_func(**kwargs) # Call the imported tool function
        return str(result) # Ensure string output for Gradio

    return gradio_wrapper_func, inputs, name, description

def setup_tools(server):
    """Setup tools and return the Gradio interface"""
    log_info("Starting tool setup...")
    tools_data = get_tools_from_filemaker()
    log_info(f"Retrieved {len(tools_data)} tools from FileMaker")

    # Create Gradio interface
    with gr.Blocks() as demo:
        gr.Markdown("# FileMaker MCP Tools")
        
        # Create and register tools dynamically
        for tool_data in tools_data:
            try:
                tool_name = tool_data['function']['name']
                log_info(f"Creating tool: {tool_name}")
                
                # Create the dynamic tool function
                tool_func = create_dynamic_tool(tool_data)
                log_info(f"Successfully created function for {tool_name}")

                # Register with MCP
                server.tool(name=tool_name)(tool_func)
                log_info(f"Registered MCP tool: {tool_name}")

                # Create Gradio interface
                log_info(f"Creating Gradio interface for {tool_name}")
                gradio_func, inputs, name, description = create_gradio_tool(tool_name, tool_func, tool_data)
                with gr.Tab(name):
                    gr.Markdown(f"**{description}**")
                    btn = gr.Button(f"Run {name}")
                    output = gr.Textbox(label="Result")
                    btn.click(gradio_func, inputs=inputs, outputs=output)
                log_info(f"Created Gradio UI for tool: {tool_name}")
            except Exception as e:
                import traceback
                log_error(f"Error creating tool {tool_data.get('function', {}).get('name', 'unknown')}: {e}")
                log_error(f"Error details: {str(e)}")
                log_error(f"Traceback: {traceback.format_exc()}")
                # Continue with other tools even if one fails
                continue

    return demo

def main():
    """Main function to run the server"""
    try:
        # Create MCP server first
        log_info("Initializing MCP server...")
        server = FastMCP("FileMaker Tools")
        
        # Setup tools and get Gradio interface
        log_info("Setting up tools and Gradio interface...")
        demo = setup_tools(server)
        
        # Start Gradio server in a separate thread
        log_info("Starting Gradio server...")
        gradio_thread = threading.Thread(target=demo.launch, kwargs={'server_port': 7860})
        gradio_thread.daemon = True  # Make thread daemon so it exits when main thread exits
        gradio_thread.start()
        log_info("Gradio server started in background thread")

        # Run MCP server in the main thread
        log_info("Starting FastMCP server with stdio transport...")
        server.run(transport='stdio')

    except Exception as e:
        import traceback
        log_error("MCP server crashed during launch: " + str(e))
        log_error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()