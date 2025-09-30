"""
aloe_patch
==========

Monkeypatch Aloe and related dependencies for Python 3.13+ compatibility.

Fixes:
- Removes deprecated "U" flag from gherkin.token_scanner.io.open
- Sanitizes Aloe-generated ASTs so Python 3.13's stricter validation accepts them
"""

import ast
import io

import aloe.codegen
import gherkin.token_scanner

# Patch gherkin: remove deprecated "U" mode from open()

_original_open = io.open


def patched_open(
    path, mode="r", buffering=-1, encoding=None, errors=None, newline=None
):
    """Drop the deprecated 'U' flag if present in mode strings."""
    mode = mode.replace("U", "")
    return _original_open(path, mode, buffering, encoding, errors, newline)


gherkin.token_scanner.io.open = patched_open

# Patch aloe: sanitize AST before compile()

_old_compile = compile


def sanitize_ast(node):
    """Ensure AST line/column ranges are valid for Python 3.13+."""
    for child in ast.walk(node):
        if hasattr(child, "lineno") and hasattr(child, "end_lineno"):
            if child.end_lineno < child.lineno:
                child.end_lineno = child.lineno
        if hasattr(child, "col_offset") and hasattr(child, "end_col_offset"):
            if child.end_col_offset < child.col_offset:
                child.end_col_offset = child.col_offset
    return node


def safe_compile(tree, filename, mode, **kwargs):
    """Replacement for compile() that sanitizes AST nodes before execution."""
    if isinstance(tree, ast.AST):
        tree = sanitize_ast(ast.fix_missing_locations(tree))
    return _old_compile(tree, filename, mode, **kwargs)


aloe.codegen.compile = safe_compile
