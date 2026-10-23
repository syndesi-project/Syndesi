#!/usr/bin/env python3
# File : gen_sync.py
# Author : Sébastien Deriaz
# License : GPL
"""
Generate a blocking sync class from an AsyncXxx class. Never touches the
input file. This is the mirror image of gen_async.py, but going the other
way - and the safer direction: removing concurrency ceremony (await/async)
cannot introduce a wrong scheduling decision the way inserting it can, so
this generator can afford to be strict and self-contained instead of
wrapping a sync instance.

    mydriver_async.py                mydriver.py
    +---------------------------+    +------------------------+
    | class AsyncMyInstrument(  |    | class MyInstrument(     |
    |         AsyncProtocol):   |    |         Protocol):      |
    |   async def measure(self):|--->|   def measure(self):    |
    |     await self.write(...) |    |     self.write(...)     |
    |     return await self...  |    |     return self...      |
    +---------------------------+    +------------------------+

Usage:
    python scripts/gen_sync.py mydriver_async.py       -> mydriver.py
    python scripts/gen_sync.py mydriver_async.py -o out.py

Convention driving the whole transform: any identifier "AsyncXxx" names the
async counterpart of "Xxx" - this holds for the class itself, its bases,
generic parameters, annotations, and imports. There is no lookup table to
maintain per project; it is expected to hold for every driver author's own
classes too.

Rules applied to each AsyncFunctionDef method of a top-level AsyncXxx class
(see CONFIG to extend them):
    A) async def foo(...)   -> def foo(...)
    B) await EXPR            -> EXPR
    C) async with X:          -> with X:
    D) async for X in Y:      -> for X in Y:
    E) AsyncFoo               -> Foo                      (everywhere: bases,
       annotations, generic args, instantiations, isinstance checks)
    F) asyncio.sleep/Lock/... -> time.sleep/threading.Lock/...  (CALL_SUBSTITUTIONS)
    G) __aenter__/__aexit__/__aiter__/__anext__ -> their sync dunder names

A method decorated @no_sync (syndesi.tools.asyncify.no_sync) gets a stub in
the generated class that raises NotImplementedError instead of a converted
body - use it for methods with no meaningful blocking equivalent (built on
asyncio.gather/TaskGroup/Queue and the like).

Not a general transpiler. Any asyncio.* reference left over after rule F
(i.e. not in CALL_SUBSTITUTIONS) makes generation fail loudly, naming the
offending line - on purpose: a silently-wrong sync twin is worse than a
generator that refuses to guess. Mark the method @no_sync instead, or add
the primitive to CALL_SUBSTITUTIONS if it truly has a safe sync equivalent.
"""

from __future__ import annotations

import argparse
import ast
import copy
from pathlib import Path

# ---- rules ----

NO_SYNC_DECORATOR = "no_sync"

# asyncio.<attr> -> "<module>.<attr>" it should become in the sync twin.
# Anything encountered that is NOT in this table aborts generation (see rule F).
CALL_SUBSTITUTIONS: dict[str, str] = {
    "asyncio.sleep": "time.sleep",
    "asyncio.Lock": "threading.Lock",
    "asyncio.Event": "threading.Event",
    "asyncio.Condition": "threading.Condition",
}

# Modules that CALL_SUBSTITUTIONS may introduce - imported only if actually used.
_SUBSTITUTION_MODULES = ("time", "threading")

METHOD_SUBSTITUTIONS: dict[str, str] = {
    "__aenter__": "__enter__",
    "__aexit__": "__exit__",
    "__aiter__": "__iter__",
    "__anext__": "__next__",
}


def output_path(input_path: Path) -> Path:
    stem = input_path.stem
    stem = stem[: -len("_async")] if stem.endswith("_async") else stem + "_sync"
    return input_path.with_stem(stem)


def _strip_async_prefix(name: str) -> str:
    if name.startswith("Async") and len(name) > 5 and name[5].isupper():
        return name[5:]
    return name


def _module_without_async_suffix(module: str) -> str:
    parts = module.split(".")
    parts[-1] = parts[-1][: -len("_async")] if parts[-1].endswith("_async") else parts[-1]
    return ".".join(parts)


# ---- transform ----


class _AsyncStripper(ast.NodeTransformer):
    """Removes async/await ceremony and applies name substitutions. Safe to run
    on already-sync nodes too (e.g. a plain __init__): every visit_* here is a
    no-op unless the pattern it targets is actually present."""

    def visit_Await(self, node: ast.Await) -> ast.AST:
        self.generic_visit(node)
        return node.value

    def visit_AsyncWith(self, node: ast.AsyncWith) -> ast.With:
        self.generic_visit(node)
        return ast.copy_location(ast.With(items=node.items, body=node.body), node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.For:
        self.generic_visit(node)
        new = ast.For(target=node.target, iter=node.iter, body=node.body, orelse=node.orelse)
        return ast.copy_location(new, node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.value, ast.Name):
            sub = CALL_SUBSTITUTIONS.get(f"{node.value.id}.{node.attr}")
            if sub is not None:
                mod, _, attr = sub.rpartition(".")
                new = ast.Attribute(value=ast.Name(id=mod, ctx=ast.Load()), attr=attr, ctx=node.ctx)
                return ast.copy_location(new, node)
        if node.attr in METHOD_SUBSTITUTIONS:
            node.attr = METHOD_SUBSTITUTIONS[node.attr]
        return node

    def visit_Name(self, node: ast.Name) -> ast.Name:
        node.id = _strip_async_prefix(node.id)
        return node


def _decorator_name(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    return None


def _has_decorator(func: ast.AsyncFunctionDef, name: str) -> bool:
    return any(_decorator_name(d) == name for d in func.decorator_list)


def _check_no_leftover_async(node: ast.AST, context: str) -> None:
    for child in ast.walk(node):
        if isinstance(child, (ast.Await, ast.AsyncWith, ast.AsyncFor, ast.AsyncFunctionDef)):
            raise SystemExit(
                f"gen_sync: unhandled async construct in {context}: "
                f"{ast.unparse(child).splitlines()[0]!r}"
            )
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "asyncio"
        ):
            raise SystemExit(
                f"gen_sync: {context} uses 'asyncio.{child.attr}' with no sync equivalent "
                f"in CALL_SUBSTITUTIONS. Add one, or mark the method @no_sync."
            )


def _build_no_sync_stub(func: ast.AsyncFunctionDef) -> ast.FunctionDef:
    body: list[ast.stmt] = [
        ast.Raise(
            exc=ast.Call(
                func=ast.Name(id="NotImplementedError", ctx=ast.Load()),
                args=[ast.Constant(value=f"{func.name}() is only available in async mode")],
                keywords=[],
            ),
            cause=None,
        )
    ]
    stub = ast.FunctionDef(
        name=func.name,
        args=_AsyncStripper().visit(copy.deepcopy(func.args)),
        body=body,
        decorator_list=[],
        returns=copy.deepcopy(func.returns),
        type_comment=None,
    )
    return ast.fix_missing_locations(stub)


def _convert_method(func: ast.AsyncFunctionDef) -> ast.FunctionDef:
    body = [_AsyncStripper().visit(copy.deepcopy(stmt)) for stmt in func.body]
    twin = ast.FunctionDef(
        name=METHOD_SUBSTITUTIONS.get(func.name, func.name),
        args=_AsyncStripper().visit(copy.deepcopy(func.args)),
        body=body,
        decorator_list=[
            _AsyncStripper().visit(copy.deepcopy(d))
            for d in func.decorator_list
            if _decorator_name(d) != NO_SYNC_DECORATOR
        ],
        returns=copy.deepcopy(func.returns),
        type_comment=None,
    )
    twin = ast.fix_missing_locations(twin)
    _check_no_leftover_async(twin, f"{func.name}()")
    return twin


def _convert_class(cls: ast.ClassDef) -> ast.ClassDef:
    new_body: list[ast.stmt] = []
    for stmt in cls.body:
        if isinstance(stmt, ast.AsyncFunctionDef):
            if _has_decorator(stmt, NO_SYNC_DECORATOR):
                new_body.append(_build_no_sync_stub(stmt))
            else:
                new_body.append(_convert_method(stmt))
        else:
            new_body.append(_AsyncStripper().visit(copy.deepcopy(stmt)))

    new_cls = ast.ClassDef(
        name=_strip_async_prefix(cls.name),
        bases=[_AsyncStripper().visit(copy.deepcopy(b)) for b in cls.bases],
        keywords=copy.deepcopy(cls.keywords),
        body=new_body,
        decorator_list=[_AsyncStripper().visit(copy.deepcopy(d)) for d in cls.decorator_list],
    )
    return ast.fix_missing_locations(new_cls)


def _convert_imports(source: str, tree: ast.Module) -> tuple[list[str], list[str]]:
    """Returns (future_imports, other_imports) - kept apart because
    `from __future__ import ...` must stay the first statement(s) in the file."""
    future_imports: list[str] = []
    imports: list[str] = []
    for n in tree.body:
        if isinstance(n, ast.Import):
            # "import asyncio" is dropped; anything else is copied as-is.
            if any(a.name == "asyncio" for a in n.names):
                continue
            segment = ast.get_source_segment(source, n)
            if segment is not None:
                imports.append(segment)
        elif isinstance(n, ast.ImportFrom):
            if n.module == "__future__":
                segment = ast.get_source_segment(source, n)
                if segment is not None:
                    future_imports.append(segment)
                continue
            module = _module_without_async_suffix(n.module) if n.module else n.module
            names = ", ".join(
                _strip_async_prefix(a.name)
                + (f" as {_strip_async_prefix(a.asname)}" if a.asname else "")
                for a in n.names
            )
            prefix = "." * n.level
            imports.append(f"from {prefix}{module or ''} import {names}")
    return future_imports, imports


def _drop_unused_imports(imports: list[str], body: str) -> list[str]:
    used = {n.id for n in ast.walk(ast.parse(body)) if isinstance(n, ast.Name)}
    kept: list[str] = []
    for stmt in imports:
        (node,) = ast.parse(stmt).body
        assert isinstance(node, (ast.Import, ast.ImportFrom))
        bound = [a.asname or a.name for a in node.names]
        live = [a for a, name in zip(node.names, bound) if name in used]
        if not live:
            continue
        if len(live) == len(node.names):
            kept.append(stmt)
        else:
            live_names = ", ".join(
                a.name + (f" as {a.asname}" if a.asname else "") for a in live
            )
            prefix = "." * node.level if isinstance(node, ast.ImportFrom) else ""
            module = getattr(node, "module", None) or ""
            kept.append(f"from {prefix}{module} import {live_names}")
    return kept


def generate(source: str) -> str:
    tree = ast.parse(source)

    future_imports, imports = _convert_imports(source, tree)

    classes: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Async"):
            classes.append(ast.unparse(_convert_class(node)))

    if not classes:
        raise SystemExit("no class named AsyncXxx found")

    body = "\n\n\n".join(classes)
    imports = _drop_unused_imports(imports, body)
    for mod in _SUBSTITUTION_MODULES:
        if f"{mod}." in body and f"import {mod}" not in imports:
            imports.insert(0, f"import {mod}")

    return "\n".join(future_imports + imports) + "\n\n\n" + body + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a blocking sync class.")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()

    out = args.output or output_path(args.input)
    if out.resolve() == args.input.resolve():
        raise SystemExit("refusing to overwrite the input file")

    out.write_text(generate(args.input.read_text()))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
