import os
import sys
import ast

MCP_TOOL_DECORATOR = "mcp.tool"

def _get_decorator_name(attr: ast.expr) -> str:
    """Extract decorator name from AST node."""
    if isinstance(attr, ast.Name):
        return attr.id
    if isinstance(attr, ast.Attribute) and getattr(attr.value, "id", "") == "mcp" and attr.attr == "tool":
        return MCP_TOOL_DECORATOR
    if isinstance(attr, ast.Call) and isinstance(attr.func, ast.Attribute):
        if getattr(attr.func.value, "id", "") == "mcp" and attr.func.attr == "tool":
            return MCP_TOOL_DECORATOR
    return ""

def _check_file_for_mcp_tool(filename: str) -> list[str]:
    """Check a single file for @mcp.tool decorators and return errors."""
    if not os.path.exists(filename):
        return []
        
    try:
        with open(filename, "r") as f:
            content = f.read()
            
        tree = ast.parse(content)
        errors = []
        for node in getattr(tree, 'body', []):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for attr in getattr(node, 'decorator_list', []):
                if _get_decorator_name(attr) == MCP_TOOL_DECORATOR:
                    errors.append(f"Error: {filename} contains @mcp.tool on function {node.name}")
        return errors
    except Exception as e:
        return [f"Could not parse {filename}: {e}"]

def verify_tier_3_tools() -> None:
    """Verify that no Tier 3 tool file uses @mcp.tool."""
    files = [
        "src/mem_graph/tools/filesystem/filesystem.py",
        "src/mem_graph/tools/filesystem/status.py",
        "src/mem_graph/tools/filesystem/tree.py",
        "src/mem_graph/tools/graph/graph_queries.py",
        "src/mem_graph/tools/code/parser.py",
        "src/mem_graph/tools/sandbox/session.py",
    ]
    
    errors: list[str] = []
    
    for filename in files:
        errors.extend(_check_file_for_mcp_tool(filename))
            
    if errors:
        for err in errors:
            print(err)
        sys.exit(1)
    else:
        print("Success: No Tier 3 tools contain @mcp.tool decorators.")
        sys.exit(0)

if __name__ == "__main__":
    verify_tier_3_tools()
