.PHONY: run inspect

# Starting the server with uv run main.py
run:
	uv run main.py

# Start the FastMCP Inspector UI for testing tools and connecting to it with Transport Type: Streamable HTTP, URL: http://localhost:9100/mcp
inspect:
	npx @modelcontextprotocol/inspector http://localhost:9100/mcp
