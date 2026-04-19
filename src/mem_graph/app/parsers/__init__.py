"""Tree-sitter parser pipeline for mem-graph code indexing.

Public API:
  parse_file(path, language=None, limits=None) → ParseResult
  extract_file(path, language=None, limits=None) → (ParseResult, nodes, edges)
  index_file(root, path, ...) → PersistenceResult
  index_tree(root, ...) → list[PersistenceResult]
"""

from .pipeline import extract_file, index_file, index_tree, parse_file

__all__ = ["extract_file", "index_file", "index_tree", "parse_file"]
