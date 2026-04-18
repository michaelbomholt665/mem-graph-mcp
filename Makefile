.PHONY: run inspect evals evals-ci evals-live evals-release evals-report

# Starting the server with uv run main.py
run:
	uv run main.py

# Start the FastMCP Inspector UI for testing tools and connecting to it with Transport Type: Streamable HTTP, URL: http://localhost:9100/mcp
inspect:
	npx @modelcontextprotocol/inspector http://localhost:9100/mcp

# Run the baseline eval suites in deterministic fixture mode
evals:
	uv run mem-graph-evals --mode fixture --output build/evals/fixture-report.json

# Fast deterministic gate for CI and pre-merge validation
evals-ci:
	uv run mem-graph-evals --mode fixture --runs 1 --output build/evals/ci-report.json

# Full live-agent eval run for manual debugging
evals-live:
	uv run mem-graph-evals --mode live --output build/evals/live-report.json

# Slower release-time live eval run
evals-release:
	uv run mem-graph-evals --mode live --runs 3 --output build/evals/release-report.json

# Print the current fixture report and refresh the JSON artifact
evals-report:
	uv run mem-graph-evals --mode fixture --json --output build/evals/fixture-report.json
