"""Interactive selection dialogs for the ANVAYA CLI."""

from __future__ import annotations

from typing import Any

from prompt_toolkit.shortcuts import radiolist_dialog


def select_one(
    title: str,
    items: list[tuple[str, str]],
    no_items_message: str = "No items to select.",
) -> str | None:
    """Show an in-terminal list selector and return the chosen key.

    Returns ``None`` if the user cancels with ``Escape`` or ``Ctrl-C``.
    """
    if not items:
        return None
    values = [(key, label) for key, label in items]
    result = radiolist_dialog(
        title=title,
        values=values,
    ).run()
    return result


def select_model(models: list[dict[str, Any]], current_id: str = "") -> dict[str, Any] | None:
    """Select a model from the normalized catalog."""
    items: list[tuple[str, str]] = []
    for m in models:
        status = m.get("availability", "unknown")
        marker = "●" if status in ("available", "configured") else "○"
        label = f"{marker} {m.get('display_name', m['id'])} · {m.get('provider', '')}"
        items.append((m["id"], label))
    selected_id = select_one("SELECT MODEL", items)
    if not selected_id:
        return None
    return next((m for m in models if m["id"] == selected_id), None)


def select_project(projects: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Select a project and return (project_id, name)."""
    items = [(p["project_id"], p.get("name", p["project_id"])) for p in projects]
    selected_id = select_one("SELECT PROJECT", items)
    if not selected_id:
        return None
    p = next((p for p in projects if p["project_id"] == selected_id), {})
    return selected_id, p.get("name", selected_id)


def select_profile(profiles: list[dict[str, Any]]) -> str | None:
    """Select a profile ID."""
    items = [(p["id"], p.get("display_name", p["id"])) for p in profiles]
    return select_one("SELECT PROFILE", items)


def confirm_deletion(name: str) -> bool:
    """Show a yes/no selector for destructive operations."""
    result = radiolist_dialog(
        title=f"Delete {name}?",
        values=[("cancel", "Cancel"), ("delete", "Delete")],
    ).run()
    return result == "delete"
