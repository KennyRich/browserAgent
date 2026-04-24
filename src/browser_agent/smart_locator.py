"""AX tree-based element indexing with semantic enrichment and embedding search."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from playwright.async_api import Page
from rapidfuzz import fuzz


INTERACTIVE_ROLES = frozenset({
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "listbox", "menuitem", "menuitemcheckbox", "menuitemradio",
    "tab", "searchbox", "switch", "slider", "spinbutton",
    "option", "treeitem",
})

STRUCTURAL_ROLES = frozenset({
    "form", "navigation", "main", "dialog", "region",
    "article", "complementary", "banner", "contentinfo",
})


@dataclass
class Element:
    backend_node_id: int
    role: str
    name: str
    description: str
    value: str
    parent_path: list[str] = field(default_factory=list)
    siblings_before: list[str] = field(default_factory=list)
    nearest_heading: str | None = None
    nearest_label: str | None = None
    in_form: bool = False

    def to_text(self) -> str:
        parts = [f"role={self.role}"]
        if self.name:
            parts.append(f'name="{self.name}"')
        if self.value:
            parts.append(f'value="{self.value}"')
        if self.description:
            parts.append(f'desc="{self.description}"')
        if self.nearest_label:
            parts.append(f'labeled-by="{self.nearest_label}"')
        if self.nearest_heading:
            parts.append(f'under-heading="{self.nearest_heading}"')
        if self.in_form:
            parts.append("inside-form")
        if self.siblings_before:
            parts.append(f"preceded-by={self.siblings_before[-2:]}")
        if self.parent_path:
            parts.append(f"within={' > '.join(self.parent_path[-3:])}")
        return " | ".join(parts)

    def fingerprint(self) -> str:
        key = f"{self.role}|{self.name}|{self.nearest_heading}|{'/'.join(self.parent_path)}"
        return hashlib.md5(key.encode()).hexdigest()[:12]


def _prop(node: dict, key: str) -> str:
    v = node.get(key)
    if isinstance(v, dict):
        return v.get("value", "") or ""
    return v or ""


class PageIndex:
    def __init__(self) -> None:
        self.elements: list[Element] = []
        self.embeddings: np.ndarray | None = None
        self.url: str = ""

    async def build(self, page: Page, model: Any) -> None:
        self.url = page.url
        client = await page.context.new_cdp_session(page)
        try:
            result = await client.send("Accessibility.getFullAXTree")
        finally:
            await client.detach()

        nodes = result["nodes"]
        by_id = {n["nodeId"]: n for n in nodes}
        elements: list[Element] = []

        def walk(
            node: dict,
            parent_path: list[str],
            in_form: bool,
            nearest_heading: str | None,
            nearest_label: str | None,
            sibling_names: list[str],
        ) -> None:
            if node.get("ignored"):
                for cid in node.get("childIds", []):
                    if cid in by_id:
                        walk(by_id[cid], parent_path, in_form, nearest_heading,
                             nearest_label, sibling_names)
                return

            role = _prop(node, "role")
            name = _prop(node, "name").strip()
            desc = _prop(node, "description").strip()
            val = _prop(node, "value").strip()

            if role == "heading" and name:
                nearest_heading = name
            new_in_form = in_form or role == "form"

            if role in INTERACTIVE_ROLES and (name or val or desc):
                elements.append(Element(
                    backend_node_id=node.get("backendDOMNodeId", 0),
                    role=role,
                    name=name,
                    description=desc,
                    value=val,
                    parent_path=parent_path.copy(),
                    siblings_before=sibling_names.copy(),
                    nearest_heading=nearest_heading,
                    nearest_label=nearest_label,
                    in_form=new_in_form,
                ))

            if role in STRUCTURAL_ROLES or role == "heading":
                tag = f"{role}:{name}" if name else role
                new_path = parent_path + [tag]
            else:
                new_path = parent_path

            child_siblings: list[str] = []
            for cid in node.get("childIds", []):
                if cid not in by_id:
                    continue
                child = by_id[cid]
                walk(child, new_path, new_in_form, nearest_heading,
                     nearest_label, child_siblings)
                cname = _prop(child, "name").strip()
                if cname:
                    child_siblings.append(cname)

        roots = [n for n in nodes if not n.get("parentId")]
        for root in roots:
            walk(root, [], False, None, None, [])

        seen: set[tuple] = set()
        unique: list[Element] = []
        for el in elements:
            key = (el.backend_node_id, el.role, el.name)
            if key in seen:
                continue
            seen.add(key)
            unique.append(el)
        self.elements = unique

        if self.elements:
            texts = [e.to_text() for e in self.elements]
            self.embeddings = model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False,
            )

    def search(
        self,
        intent: str,
        model: Any,
        top_k: int = 5,
        fuzzy_weight: float = 0.25,
    ) -> list[tuple[Element, float]]:
        if self.embeddings is None or not self.elements:
            return []
        q = model.encode(intent, normalize_embeddings=True, show_progress_bar=False)
        semantic = self.embeddings @ q
        fuzzy = np.array([
            fuzz.partial_ratio(intent.lower(), (e.name or "").lower()) / 100.0
            for e in self.elements
        ])
        combined = (1 - fuzzy_weight) * semantic + fuzzy_weight * fuzzy
        top = np.argsort(-combined)[:top_k]
        return [(self.elements[i], float(combined[i])) for i in top]
