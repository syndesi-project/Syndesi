#!/usr/bin/env python3
# File : gen_async.py
# Author : Sébastien Deriaz
# License : GPL
"""
Generate an async wrapper class from @asyncify-marked sync methods.
Never touches the input file.

    adapter.py                       adapter_async.py
    +--------------------+           +--------------------------+
    | class Adapter:     |           | class AsyncAdapter:      |
    |   def open(): ...  |   --->    |   def __init__(self,     |
    |                     |           |                sync):    |
    |   @asyncify         |           |     self.sync = sync     |
    |   def close(): ...  |           |   async def close(self): |
    +--------------------+           |     await asyncio.wrap.. |
                                       +--------------------------+

Usage:
    python scripts/gen_async.py adapter.py            -> adapter_async.py
    python scripts/gen_async.py adapter.py -o out.py

Rules inside a marked method's body (see CONFIG to change them):
    A) EXPR.result(ARGS)  -> await asyncio.wrap_future(EXPR)
    B) self.name(ARGS)    -> await self.name(ARGS)     if name is also marked
    C) self.x             -> self.sync.x                otherwise
    D) with LOCK:          -> async with LOCK:  (+ NAME_SUBSTITUTIONS)

Not a general transpiler, only this shape. Doesn't follow calls through an
attribute other than `self` (e.g. `self.adapter.open()`) - those get rule C
on `self.adapter` but the call itself is left sync, unawaited. Don't mark
a method like that; write its twin by hand.

A method whose sync/async bodies genuinely differ (e.g. Adapter.open(),
which computes a timeout the async side doesn't need) still gets converted,
just imperfectly - don't mark it either.
"""

from __future__ import annotations

import argparse
import ast
import copy
from pathlib import Path

# ---- rules ----

MARKER_DECORATOR = "asyncify"
RESULT_METHOD_NAME = "result"
WRAPPED_ATTR = "sync"


def output_path(input_path: Path) -> Path:
    return input_path.with_stem(input_path.stem + "_async")


def async_class_name(name: str) -> str:
    return f"Async{name}"


NAME_SUBSTITUTIONS: dict[str, str] = {
    "_sync_io_lock": "_async_io_lock",
}

ASYNC_TWIN_METHOD_NAMES: set[str] = {
    "open", "close", "read", "read_detailed", "write",
    "flush_read", "query", "query_detailed",
}

# ---- transform ----


class _BodyRewriter(ast.NodeTransformer):
    def visit_With(self, node: ast.With) -> ast.AsyncWith:
        self.generic_visit(node)
        return ast.copy_location(ast.AsyncWith(items=node.items, body=node.body), node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func = node.func

        # A: EXPR.result(ARGS) -> await asyncio.wrap_future(EXPR)
        if isinstance(func, ast.Attribute) and func.attr == RESULT_METHOD_NAME:
            wrap = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="asyncio", ctx=ast.Load()),
                    attr="wrap_future", ctx=ast.Load(),
                ),
                args=[func.value], keywords=[],
            )
            return ast.copy_location(ast.Await(value=wrap), node)

        # B: self.name(ARGS) -> await self.name(ARGS)
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
            and func.attr in ASYNC_TWIN_METHOD_NAMES
        ):
            return ast.copy_location(ast.Await(value=node), node)

        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        self.generic_visit(node)
        if node.attr in NAME_SUBSTITUTIONS:
            node.attr = NAME_SUBSTITUTIONS[node.attr]
        # C: self.x -> self.sync.x, unless x is a sibling async method
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node.attr not in ASYNC_TWIN_METHOD_NAMES
        ):
            node.value = ast.Attribute(value=node.value, attr=WRAPPED_ATTR, ctx=ast.Load())
        return node


def _decorator_name(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    return None


def _is_marked(func: ast.FunctionDef) -> bool:
    return any(_decorator_name(d) == MARKER_DECORATOR for d in func.decorator_list)


def _build_method(func: ast.FunctionDef) -> ast.AsyncFunctionDef:
    body = [_BodyRewriter().visit(copy.deepcopy(stmt)) for stmt in func.body]

    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body[0] = ast.Expr(value=ast.Constant(value=f"Async version of {func.name}()."))

    twin = ast.AsyncFunctionDef(
        name=func.name,
        args=copy.deepcopy(func.args),
        body=body,
        decorator_list=[],
        returns=copy.deepcopy(func.returns),
        type_comment=None,
    )
    return ast.fix_missing_locations(twin)


def _build_class(cls: ast.ClassDef, methods: list[ast.AsyncFunctionDef]) -> ast.ClassDef:
    init = ast.parse(
        f"def __init__(self, {WRAPPED_ATTR}: {cls.name}) -> None:\n"
        f"    self.{WRAPPED_ATTR} = {WRAPPED_ATTR}\n"
    ).body[0]
    new_cls = ast.ClassDef(
        name=async_class_name(cls.name),
        bases=[], keywords=[],
        body=[init, *methods],
        decorator_list=[],
    )
    return ast.fix_missing_locations(new_cls)


def generate(source: str, module_stem: str) -> str:
    tree = ast.parse(source)

    imports: list[str] = []
    for n in tree.body:
        if not isinstance(n, (ast.Import, ast.ImportFrom)):
            continue
        segment = ast.get_source_segment(source, n)
        if segment is not None:
            imports.append(segment)

    classes: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        marked = [n for n in node.body if isinstance(n, ast.FunctionDef) and _is_marked(n)]
        if not marked:
            continue
        imports.append(f"from .{module_stem} import {node.name}")
        methods = [_build_method(m) for m in marked]
        classes.append(ast.unparse(_build_class(node, methods)))

    if not classes:
        raise SystemExit("no @asyncify-marked method found")

    return "\n".join(imports) + "\n\n\n" + "\n\n\n".join(classes) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an async wrapper class.")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()

    out = args.output or output_path(args.input)
    if out.resolve() == args.input.resolve():
        raise SystemExit("refusing to overwrite the input file")

    out.write_text(generate(args.input.read_text(), args.input.stem))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
