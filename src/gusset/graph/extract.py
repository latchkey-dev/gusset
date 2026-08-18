"""Per-file symbol and reference extraction via tree-sitter.

Manual AST walks (no query DSL) — immune to query-API drift across
py-tree-sitter versions and explicit about exactly what we extract.

Phase 1 ships Python; TypeScript/JavaScript and Go follow the same
Extraction contract so extractors stay independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
}


@dataclass
class Def:
    name: str
    qualname: str  # dotted path within the file, module prefix added by indexer
    kind: str      # class | function | method
    start_line: int
    end_line: int


@dataclass
class Ref:
    """A reference from `scope` (in-file qualname, '' = module level) to `target_name`."""

    scope: str
    target_name: str   # bare name for calls/inherits; dotted module path for imports
    kind: str          # calls | imports | inherits
    line: int


@dataclass
class Extraction:
    defs: list[Def] = field(default_factory=list)
    refs: list[Ref] = field(default_factory=list)


def extract(source: bytes, language: str) -> Extraction:
    if language != "python":
        raise ValueError(f"unsupported language: {language}")
    tree = get_parser(language).parse(source)
    ex = Extraction()
    _walk_python(tree.root_node, source, scope=[], in_class=False, out=ex)
    return ex


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _callee_name(node: Node, source: bytes) -> str | None:
    """Rightmost name of a call target: `f(...)` -> f, `a.b.f(...)` -> f."""
    if node.type == "identifier":
        return _text(node, source)
    if node.type == "attribute":
        attr = node.child_by_field_name("attribute")
        return _text(attr, source) if attr is not None else None
    return None


def _walk_python(
    node: Node, source: bytes, scope: list[str], in_class: bool, out: Extraction
) -> None:
    scope_qual = ".".join(scope)

    if node.type in ("function_definition", "class_definition"):
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _text(name_node, source)
        qualname = ".".join([*scope, name])
        if node.type == "class_definition":
            kind = "class"
            # Base classes: class Child(Base, mixin.Other) -> inherits edges.
            supers = node.child_by_field_name("superclasses")
            if supers is not None:
                for child in supers.named_children:
                    base = _callee_name(child, source)
                    if base is not None and base != "object":
                        out.refs.append(
                            Ref(qualname, base, "inherits", child.start_point[0] + 1)
                        )
        else:
            kind = "method" if in_class else "function"
        out.defs.append(
            Def(name, qualname, kind, node.start_point[0] + 1, node.end_point[0] + 1)
        )
        body = node.child_by_field_name("body")
        if body is not None:
            _walk_python(
                body, source, [*scope, name], node.type == "class_definition", out
            )
        return

    if node.type == "call":
        fn = node.child_by_field_name("function")
        if fn is not None:
            callee = _callee_name(fn, source)
            if callee is not None:
                out.refs.append(
                    Ref(scope_qual, callee, "calls", node.start_point[0] + 1)
                )
        # Recurse for nested calls / lambdas in arguments.
        for child in node.named_children:
            _walk_python(child, source, scope, in_class, out)
        return

    if node.type == "import_statement":
        for child in node.named_children:
            target = child.child_by_field_name("name") if child.type == "aliased_import" else child
            if target is not None and target.type in ("dotted_name", "identifier"):
                out.refs.append(
                    Ref(scope_qual, _text(target, source), "imports", node.start_point[0] + 1)
                )
        return

    if node.type == "import_from_statement":
        module = node.child_by_field_name("module_name")
        if module is not None:
            out.refs.append(
                Ref(scope_qual, _text(module, source), "imports", node.start_point[0] + 1)
            )
        return

    for child in node.named_children:
        _walk_python(child, source, scope, in_class, out)
