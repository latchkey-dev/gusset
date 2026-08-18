"""Per-file symbol and reference extraction via tree-sitter.

Manual AST walks (no query DSL) — immune to query-API drift across
py-tree-sitter versions and explicit about exactly what we extract.

Python, TypeScript/JavaScript, and Go all share the same Extraction
contract so extractors stay independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
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
    if language == "python":
        walk = _walk_python
    elif language in ("typescript", "tsx", "javascript"):
        walk = _walk_ts
    elif language == "go":
        walk = _walk_go
    else:
        raise ValueError(f"unsupported language: {language}")
    tree = get_parser(language).parse(source)
    ex = Extraction()
    walk(tree.root_node, source, scope=[], in_class=False, out=ex)
    return ex


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _callee_name(node: Node, source: bytes) -> str | None:
    """Rightmost name of a call target: `f(...)` -> f, `a.b.f(...)` -> f."""
    if node.type == "identifier":
        return _text(node, source)
    if node.type == "attribute":  # Python: a.b
        attr = node.child_by_field_name("attribute")
        return _text(attr, source) if attr is not None else None
    if node.type == "member_expression":  # TS/JS: a.b
        prop = node.child_by_field_name("property")
        return _text(prop, source) if prop is not None else None
    if node.type == "selector_expression":  # Go: a.b
        fld = node.child_by_field_name("field")
        return _text(fld, source) if fld is not None else None
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


def _walk_ts(
    node: Node, source: bytes, scope: list[str], in_class: bool, out: Extraction
) -> None:
    """TypeScript / TSX / JavaScript. The grammars share every node type we
    touch except class heritage: TS wraps the base in an `extends_clause`
    (field `value`), JS puts the expression directly under `class_heritage`.
    """
    scope_qual = ".".join(scope)

    if node.type in ("function_declaration", "generator_function_declaration"):
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _text(name_node, source)
        qualname = ".".join([*scope, name])
        out.defs.append(
            Def(name, qualname, "function", node.start_point[0] + 1, node.end_point[0] + 1)
        )
        body = node.child_by_field_name("body")
        if body is not None:
            _walk_ts(body, source, [*scope, name], False, out)
        return

    if node.type in ("class_declaration", "abstract_class_declaration"):
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _text(name_node, source)
        qualname = ".".join([*scope, name])
        out.defs.append(
            Def(name, qualname, "class", node.start_point[0] + 1, node.end_point[0] + 1)
        )
        for child in node.named_children:
            if child.type != "class_heritage":
                continue
            for h in child.named_children:
                value = h.child_by_field_name("value") if h.type == "extends_clause" else h
                if value is None:
                    continue
                base = _callee_name(value, source)
                if base is not None:  # implements_clause etc. yield None
                    out.refs.append(
                        Ref(qualname, base, "inherits", value.start_point[0] + 1)
                    )
        body = node.child_by_field_name("body")
        if body is not None:
            _walk_ts(body, source, [*scope, name], True, out)
        return

    if node.type == "method_definition":
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _text(name_node, source)
        qualname = ".".join([*scope, name])
        out.defs.append(
            Def(name, qualname, "method", node.start_point[0] + 1, node.end_point[0] + 1)
        )
        body = node.child_by_field_name("body")
        if body is not None:
            _walk_ts(body, source, [*scope, name], False, out)
        return

    if node.type in ("lexical_declaration", "variable_declaration") and not scope:
        # Top-level `const f = () => ...` / `let g = function ...` — a def.
        for child in node.named_children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            value = child.child_by_field_name("value")
            if name_node is None or name_node.type != "identifier" or value is None:
                continue
            if value.type in ("arrow_function", "function_expression"):
                name = _text(name_node, source)
                out.defs.append(
                    Def(name, name, "function",
                        child.start_point[0] + 1, child.end_point[0] + 1)
                )
                body = value.child_by_field_name("body")
                if body is not None:
                    _walk_ts(body, source, [name], False, out)
            else:
                _walk_ts(value, source, scope, in_class, out)
        return

    if node.type in ("call_expression", "new_expression"):
        # `new X()` counts as a call to X — parity with Python, where
        # instantiation is a plain call node.
        fn = node.child_by_field_name("function") or node.child_by_field_name("constructor")
        if fn is not None:
            callee = _callee_name(fn, source)
            if callee is not None:
                out.refs.append(
                    Ref(scope_qual, callee, "calls", node.start_point[0] + 1)
                )
        for child in node.named_children:
            _walk_ts(child, source, scope, in_class, out)
        return

    if node.type == "import_statement":
        # Record the module path verbatim ("./util", "fs"); the indexer
        # resolves relative paths to in-repo modules when trivially possible.
        src_node = node.child_by_field_name("source")
        if src_node is not None:
            path = _text(src_node, source).strip("\"'`")
            out.refs.append(
                Ref(scope_qual, path, "imports", node.start_point[0] + 1)
            )
        return

    for child in node.named_children:
        _walk_ts(child, source, scope, in_class, out)


def _go_receiver_type(node: Node, source: bytes) -> str | None:
    """Receiver type name: `func (g *Greeter) M()` -> Greeter."""
    recv = node.child_by_field_name("receiver")
    if recv is None:
        return None
    for param in recv.named_children:
        if param.type != "parameter_declaration":
            continue
        t = param.child_by_field_name("type")
        if t is None:
            continue
        if t.type == "pointer_type":
            inner = t.named_children[0] if t.named_children else None
            if inner is not None:
                t = inner
        if t.type == "generic_type":
            base = t.child_by_field_name("type")
            if base is not None:
                t = base
        if t.type == "type_identifier":
            return _text(t, source)
    return None


def _walk_go(
    node: Node, source: bytes, scope: list[str], in_class: bool, out: Extraction
) -> None:
    scope_qual = ".".join(scope)

    if node.type == "function_declaration":
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _text(name_node, source)
        qualname = ".".join([*scope, name])
        out.defs.append(
            Def(name, qualname, "function", node.start_point[0] + 1, node.end_point[0] + 1)
        )
        body = node.child_by_field_name("body")
        if body is not None:
            _walk_go(body, source, [*scope, name], False, out)
        return

    if node.type == "method_declaration":
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _text(name_node, source)
        recv = _go_receiver_type(node, source)
        parts = [*scope, recv, name] if recv else [*scope, name]
        qualname = ".".join(parts)
        out.defs.append(
            Def(name, qualname, "method", node.start_point[0] + 1, node.end_point[0] + 1)
        )
        body = node.child_by_field_name("body")
        if body is not None:
            _walk_go(body, source, parts, False, out)
        return

    if node.type == "type_declaration":
        # Structs and interfaces are the closest Go analogue to classes.
        for spec in node.named_children:
            if spec.type != "type_spec":
                continue
            name_node = spec.child_by_field_name("name")
            type_node = spec.child_by_field_name("type")
            if name_node is None or type_node is None:
                continue
            if type_node.type in ("struct_type", "interface_type"):
                name = _text(name_node, source)
                out.defs.append(
                    Def(name, ".".join([*scope, name]), "class",
                        spec.start_point[0] + 1, spec.end_point[0] + 1)
                )
        return

    if node.type == "call_expression":
        fn = node.child_by_field_name("function")
        if fn is not None:
            callee = _callee_name(fn, source)
            if callee is not None:
                out.refs.append(
                    Ref(scope_qual, callee, "calls", node.start_point[0] + 1)
                )
        for child in node.named_children:
            _walk_go(child, source, scope, in_class, out)
        return

    if node.type == "import_declaration":
        # Single form: import_spec directly under the declaration.
        # Grouped form: import_spec_list wrapping the specs.
        specs = []
        for child in node.named_children:
            if child.type == "import_spec":
                specs.append(child)
            elif child.type == "import_spec_list":
                specs.extend(c for c in child.named_children if c.type == "import_spec")
        for spec in specs:
            path_node = spec.child_by_field_name("path")
            if path_node is not None:
                path = _text(path_node, source).strip('"`')
                out.refs.append(
                    Ref(scope_qual, path, "imports", spec.start_point[0] + 1)
                )
        return

    for child in node.named_children:
        _walk_go(child, source, scope, in_class, out)
