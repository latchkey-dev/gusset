"""Blast-radius SVG: structure, caps, and safe degradation."""

# stdlib ElementTree is fine here: it parses only SVG *we generated in the
# same test* — no untrusted input, so XXE/billion-laughs don't apply.
import xml.etree.ElementTree as ET

from gusset.serve.blastimage import blast_svg


def claims(n, depth=1):
    return [
        {"qualname": f"pkg.mod{i}.fn{i}", "depth": depth, "via": "pkg.seed",
         "edge_kind": "calls", "why": "w"}
        for i in range(n)
    ]


def test_svg_is_valid_xml_with_expected_elements():
    svg = blast_svg(["pkg.seed"], claims(3), [{"qualname": "pkg.bad", "reason": "r"}])
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    text = svg
    assert "pkg.seed" in text.replace("mod", "")  # seed label present
    assert text.count('stroke="#2e7d4f"') == 3    # one pass ring per verified
    assert "3 verified" in text and "1 dropped" in text


def test_overflow_is_aggregated_not_drawn():
    svg = blast_svg(["s"], claims(40), [])
    assert "+16 not drawn" in svg
    assert svg.count('stroke="#2e7d4f"') == 24    # cap holds


def test_qualname_labels_are_escaped():
    bad = [{"qualname": 'x.<script>."&y', "depth": 1, "via": "s",
            "edge_kind": "calls", "why": "w"}]
    svg = blast_svg(["s"], bad, [])
    assert "<script>" not in svg
    ET.fromstring(svg)  # still parses


def test_empty_run_renders_without_error():
    svg = blast_svg([], [], [])
    ET.fromstring(svg)
    assert "0 verified" in svg
