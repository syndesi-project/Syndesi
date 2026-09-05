#!/usr/bin/env python3
# File : gen_async.py
# Author : Sébastien Deriaz
# License : GPL
"""
Generate async twins of @asyncify-marked sync methods.

Usage:
    python scripts/gen_async.py INPUT.py [-o OUTPUT.py]

If -o is omitted, INPUT.py is updated in place.

How it works
------------
1. Any method decorated with @asyncify (see syndesi/tools/asyncify.py) is a
   candidate for async-twin generation.
2. Previously generated blocks (delimited by the GENERATED markers below)
   are stripped first, so re-running this script is always safe and
   idempotent - it never accumulates duplicates, and always reflects the
   current sync source.
3. For each candidate, a new `async def a<name>(...):` is built by copying
   the method's body and applying the rewrite rules below, then inserted
   as real source text right after the original method.
4. Everything else in the file (imports, comments, other methods,
   formatting) is left completely untouched - this script only ever
   *inserts* text, it never rewrites or reformats existing text.

Rewrite rules applied inside a marked method's body
----------------------------------------------------
  A) EXPR.result(ARGS)        -> await asyncio.wrap_future(EXPR)
     (ARGS, the command-specific timeout, has no equivalent on the async
     side - wrap_future() waits for the future unconditionally)
  B) RECEIVER.name(ARGS)      -> await RECEIVER.aname(ARGS)
     for any `name` listed in ASYNC_TWIN_METHOD_NAMES below (calling an
     already-async-ified sibling/collaborator method)
  C) `with LOCK:`              -> `async with LOCK:` (plus any name swapped
     via NAME_SUBSTITUTIONS, e.g. a sync lock for its async counterpart)

This is NOT a general-purpose sync/async transpiler - it encodes exactly
the patterns this codebase uses. A method whose sync/async bodies differ
for another reason (e.g. Adapter.open(), which computes a command-specific
timeout that the async side doesn't need at all) will still run through
these rules, but may need a manual touch-up afterwards - or simply don't
mark it and keep writing its async twin by hand, the generator will leave
it alone.

Run `ruff format` (or black) on the result afterwards if you want the
generated block reformatted to house style - this script only guarantees
valid, ast.unparse()-shaped output, not a specific style.
"""

from __future__ import annotations

import argparse
import ast
import copy
import sys
from pathlib import Path

TODO : Change this script to make a new file instead of changing the file it reads. There should be separated class. Or maybe the class could be at the end of the file
# ============================================================================
# Configuration - adjust these to change what/how code gets generated.
# ============================================================================

# Decorator name (as written in source, without the @) marking a sync
# method as having a generated async twin.
MARKER_DECORATOR = "asyncify"

# How to derive the generated method's name from the original's name.
def async_name(sync_name: str) -> str:
    return f"a{sync_name}"

# Plain identifier / attribute-name substitutions applied inside a
# converted body (e.g. swapping a sync-only lock for its async counterpart).
NAME_SUBSTITUTIONS: dict[str, str] = {
    "_sync_io_lock": "_async_io_lock",
}

# Method names known to have (or to be getting) an async twin. A call
# shaped like `RECEIVER.name(ARGS)` becomes `await RECEIVER.aname(ARGS)`
# when `name` is in this set. RECEIVER can be `self`, `self.adapter`, etc.
# - it isn't restricted to `self` because e.g. Protocol.open() calls
# self.adapter.open().
ASYNC_TWIN_METHOD_NAMES: set[str] = {
    "open", "close", "read", "read_detailed", "write",
    "flush_read", "query", "query_detailed",
}

# The name of the method that "blocks waiting for a Future's result" in
# the sync code. A call shaped like `EXPR.result(ARGS)` becomes
# `await asyncio.wrap_future(EXPR)`.
RESULT_METHOD_NAME = "result"

# Markers delimiting a previously generated block, so re-running this
# script is idempotent (never duplicates, always regenerates from scratch).
BEGIN_MARKER = "# --- BEGIN GENERATED (gen_async.py, do not edit) ---"
END_MARKER = "# --- END GENERATED (gen_async.py) ---"


# ============================================================================
# Transform
# ============================================================================


class _BodyRewriter(ast.NodeTransformer):
    """Applies the rewrite rules (A, B, C) to one function body."""

    def visit_With(self, node: ast.With) -> ast.AsyncWith:
        self.generic_visit(node)
        new_node = ast.AsyncWith(items=node.items, body=node.body)
        return ast.copy_location(new_node, node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        # Rule A: EXPR.result(ARGS) -> await asyncio.wrap_future(EXPR)
        if isinstance(node.func, ast.Attribute) and node.func.attr == RESULT_METHOD_NAME:
            wrap_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="asyncio", ctx=ast.Load()),
                    attr="wrap_future",
                    ctx=ast.Load(),
                ),
                args=[node.func.value],
                keywords=[],
            )
            return ast.copy_location(ast.Await(value=wrap_call), node)

        # Rule B: RECEIVER.name(ARGS) -> await RECEIVER.aname(ARGS)
        if isinstance(node.func, ast.Attribute) and node.func.attr in ASYNC_TWIN_METHOD_NAMES:
            node.func = ast.Attribute(
                value=node.func.value,
                attr=async_name(node.func.attr),
                ctx=ast.Load(),
            )
            return ast.copy_location(ast.Await(value=node), node)

        return node

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id in NAME_SUBSTITUTIONS:
            node.id = NAME_SUBSTITUTIONS[node.id]
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        self.generic_visit(node)
        if node.attr in NAME_SUBSTITUTIONS:
            node.attr = NAME_SUBSTITUTIONS[node.attr]
        return node


def _decorator_name(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    return None


def _is_marked(func: ast.FunctionDef) -> bool:
    return any(_decorator_name(dec) == MARKER_DECORATOR for dec in func.decorator_list)


def _build_async_twin(func: ast.FunctionDef) -> ast.AsyncFunctionDef:
    body = [copy.deepcopy(stmt) for stmt in func.body]
    rewriter = _BodyRewriter()
    body = [rewriter.visit(stmt) for stmt in body]

    # A leading docstring gets replaced - the original's wording (e.g.
    # "(blocking)") wouldn't describe the async twin correctly.
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body[0] = ast.Expr(
            value=ast.Constant(
                value=f"Async version of {func.name}(). See {func.name}() for details."
            )
        )

    twin = ast.AsyncFunctionDef(
        name=async_name(func.name),
        args=copy.deepcopy(func.args),
        body=body,
        decorator_list=[],
        returns=copy.deepcopy(func.returns),
        type_comment=None,
        lineno=func.lineno,
        col_offset=func.col_offset,
    )
    ast.fix_missing_locations(twin)
    return twin


def _strip_previous_generated_blocks(source: str) -> str:
    lines = source.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Drop the blank separator line immediately preceding a block, too,
        # so stripping is the exact inverse of insertion (see _insertion_text).
        if line.strip() == "" and i + 1 < len(lines) and BEGIN_MARKER in lines[i + 1]:
            i += 1
            continue
        if BEGIN_MARKER in line:
            i += 1
            while i < len(lines) and END_MARKER not in lines[i]:
                i += 1
            i += 1  # also skip the END marker line itself
            continue
        out.append(line)
        i += 1
    return "".join(out)


def _insertion_text(node: ast.FunctionDef, twin: ast.AsyncFunctionDef) -> str:
    indent = " " * node.col_offset
    body_lines = [indent + line if line else line for line in ast.unparse(twin).splitlines()]
    return "\n".join([""] + [indent + BEGIN_MARKER] + body_lines + [indent + END_MARKER]) + "\n"


def generate(source: str) -> str:
    """Return `source` with a generated async twin inserted after every
    @asyncify-marked method (any previous generated blocks are replaced)."""
    clean_source = _strip_previous_generated_blocks(source)
    tree = ast.parse(clean_source)

    insertions: list[tuple[int, str]] = []  # (insert-after line, text)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and _is_marked(node):
            twin = _build_async_twin(node)
            insertions.append((node.end_lineno, _insertion_text(node, twin)))

    if not insertions:
        return clean_source

    lines = clean_source.splitlines(keepends=True)
    # Bottom-to-top so an insertion never shifts a not-yet-applied line number.
    for end_line, block in sorted(insertions, key=lambda pair: pair[0], reverse=True):
        lines.insert(end_line, block)

    return "".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate async twins of @asyncify-marked sync methods."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output file (default: overwrite the input file in place)",
    )
    args = parser.parse_args()

    source = args.input.read_text()
    result = generate(source)

    output_path = args.output or args.input
    output_path.write_text(result)
    print(f"Wrote {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
