"""Minimal read-only DOM built on the stdlib HTML parser.

This is what replaces Playwright's locator API. Everything the bot needs from a
survey page -- form fields, question blocks, radio options -- is plain
server-rendered markup, so parsing it here removes the Chromium download (and
with it the only part of the project that needed an unblocked internet).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

VOID_ELEMENTS = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)
_RAW_TEXT_ELEMENTS = frozenset({"script", "style"})
_WHITESPACE = re.compile(r"\s+")


class Node:
    """One element. `children` holds child Nodes and plain str text nodes."""

    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict = None, parent: "Node" = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list = []
        self.parent = parent

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Node {self.tag} {self.attrs}>"

    def get(self, name: str, default=None):
        return self.attrs.get(name, default)

    @property
    def classes(self) -> list:
        return (self.attrs.get("class") or "").split()

    def has_class(self, name: str) -> bool:
        return name in self.classes

    def descendants(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.descendants()

    def find_all(self, tag: str = None, class_name: str = None, **attrs) -> list:
        """Descendants matching tag / CSS class / exact attribute values."""
        found = []
        for node in self.descendants():
            if tag is not None and node.tag != tag:
                continue
            if class_name is not None and not node.has_class(class_name):
                continue
            if any(node.attrs.get(key) != value for key, value in attrs.items()):
                continue
            found.append(node)
        return found

    def find(self, tag: str = None, class_name: str = None, **attrs):
        for node in self.descendants():
            if tag is not None and node.tag != tag:
                continue
            if class_name is not None and not node.has_class(class_name):
                continue
            if any(node.attrs.get(key) != value for key, value in attrs.items()):
                continue
            return node
        return None

    def text(self) -> str:
        """Visible text of the subtree, with runs of whitespace collapsed."""
        parts = []
        self._collect_text(parts)
        return _WHITESPACE.sub(" ", "".join(parts)).strip()

    def _collect_text(self, parts: list) -> None:
        if self.tag in _RAW_TEXT_ELEMENTS:
            return
        for child in self.children:
            if isinstance(child, Node):
                child._collect_text(parts)
            else:
                parts.append(child)


class _DomBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self._stack = [self.root]

    @property
    def _current(self) -> Node:
        return self._stack[-1]

    def handle_starttag(self, tag: str, attrs) -> None:
        node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self._current)
        self._current.children.append(node)
        if tag not in VOID_ELEMENTS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs) -> None:
        node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self._current)
        self._current.children.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_ELEMENTS:
            return
        # Close the nearest matching ancestor, discarding anything left unclosed
        # in between; stray end tags with no open element are ignored.
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._current.children.append(data)


def parse(html: str) -> Node:
    builder = _DomBuilder()
    builder.feed(html)
    builder.close()
    return builder.root
