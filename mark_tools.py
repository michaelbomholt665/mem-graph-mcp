import os
import re

tier_2_files = [
    "src/mem_graph/tools/memory/notes.py",
    "src/mem_graph/tools/work/projects.py",
    "src/mem_graph/tools/work/tasks.py",
    "src/mem_graph/tools/work/decisions.py",
    "src/mem_graph/tools/work/violations.py",
    "src/mem_graph/tools/agents/audit.py",
    "src/mem_graph/tools/agents/map.py",
    "src/mem_graph/tools/agents/orchestrator.py",
    "src/mem_graph/tools/agents/triage.py",
    "src/mem_graph/tools/agents/diagrams.py",
    "src/mem_graph/tools/background/task_status.py",
    "src/mem_graph/tools/integrations/jina.py",
]

hidden_files = [
    "src/mem_graph/tools/filesystem/filesystem.py",
    "src/mem_graph/tools/filesystem/status.py",
    "src/mem_graph/tools/filesystem/tree.py",
    "src/mem_graph/tools/graph/graph_queries.py",
    "src/mem_graph/tools/graph/resources.py",
    "src/mem_graph/tools/code/parser.py",
    "src/mem_graph/tools/sandbox/session.py",
]

def add_marker(filepath, marker, import_stmt):
    if not os.path.exists(filepath):
        print(f"Skipping {filepath}, file not found")
        return
    with open(filepath, "r") as f:
        content = f.read()

    if marker in content:
        return

    # add import after "from fastmcp import FastMCP"
    if "from fastmcp import FastMCP" in content:
        content = content.replace("from fastmcp import FastMCP", "from fastmcp import FastMCP\n" + import_stmt)
    elif "from fastmcp.server.utils" in content:
         content = content.replace("from fastmcp.server.utils", import_stmt + "\nfrom fastmcp.server.utils")
    else:
        # just put it near the top
        content = import_stmt + "\n" + content

    # add decorator
    content = re.sub(r'(@mcp\.tool)', f'@{marker}\n\\1', content)

    with open(filepath, "w") as f:
        f.write(content)
    print(f"Marked {filepath} with {marker}")

for f in tier_2_files:
    # Need to figure out the correct relative import depth
    depth = f.count('/') - 2 # src/mem_graph/tools is depth 0
    prefix = "." * depth if depth > 0 else "."
    imp = f"from {prefix}.markers import tier_2_tool"
    add_marker(f, "tier_2_tool", imp)

for f in hidden_files:
    depth = f.count('/') - 2
    prefix = "." * depth if depth > 0 else "."
    imp = f"from {prefix}.markers import hidden_tool"
    add_marker(f, "hidden_tool", imp)

