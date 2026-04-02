from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, cast

from rich.console import Group
from rich.rule import Rule
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, OptionList, Static, Tree

from zoterm.api.models import Collection, Item
from zoterm.services.library import ItemSnapshot, LibraryHandle, LibraryService, LibraryTree


@dataclass(frozen=True)
class NavigationTarget:
    library: LibraryHandle
    collection_key: str | None = None


class ZotermApp(App[None]):
    TITLE = "zoterm"
    SUB_TITLE = "Local Zotero browser"

    CSS = """
    Screen {
        background: #111318;
        color: #e8e6df;
    }

    #body {
        height: 1fr;
        layout: horizontal;
    }

    .pane {
        height: 1fr;
        border: solid #3d4552;
        background: #171b22;
    }

    #library-pane {
        width: 30;
    }

    #items-pane {
        width: 1fr;
        min-width: 40;
    }

    #detail-pane {
        width: 42;
        min-width: 36;
    }

    .pane-title {
        padding: 0 1;
        height: 1;
        background: #232a35;
        color: #f3efe4;
        text-style: bold;
    }

    Tree {
        padding: 0 1;
    }

    OptionList {
        padding: 0 1;
        scrollbar-size-vertical: 1;
    }

    #detail-content {
        padding: 1 2;
        scrollbar-size-vertical: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "reload", "Reload"),
        Binding("ctrl+h", "focus_libraries", "Libraries"),
        Binding("ctrl+j", "focus_items", "Items"),
    ]

    def __init__(self, service: LibraryService) -> None:
        super().__init__()
        self._service = service
        self._current_items: list[Item] = []
        self._libraries: list[LibraryTree] = []
        self._active_library: LibraryHandle | None = None
        self._loaded_detail_key: tuple[str, str] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="library-pane", classes="pane"):
                yield Static("Libraries", classes="pane-title")
                yield Tree("Libraries", id="libraries-tree")
            with Vertical(id="items-pane", classes="pane"):
                yield Static("Items", classes="pane-title")
                yield OptionList(id="items-list")
            with Vertical(id="detail-pane", classes="pane"):
                yield Static("Details", classes="pane-title")
                yield Static(id="detail-content")
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one(Tree).show_root = False
        self.query_one("#detail-content", Static).update("Loading Zotero libraries...")
        await self._refresh_libraries()

    async def on_unmount(self) -> None:
        await self._service.aclose()

    async def action_reload(self) -> None:
        self.query_one("#detail-content", Static).update("Refreshing Zotero data...")
        await self._refresh_libraries()

    def action_focus_libraries(self) -> None:
        self.query_one("#libraries-tree", Tree).focus()

    def action_focus_items(self) -> None:
        self.query_one("#items-list", OptionList).focus()

    async def on_tree_node_selected(self, event: Tree.NodeSelected[NavigationTarget]) -> None:
        target = event.node.data
        if target is None:
            return
        try:
            await self._load_items(target)
        except Exception as exc:
            self._show_error(f"Failed to load items.\n{exc}")

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        index = int(getattr(event, "index", -1))
        if index < 0 or index >= len(self._current_items):
            return
        try:
            await self._load_item_detail(self._current_items[index])
        except Exception as exc:
            self._show_error(f"Failed to load item details.\n{exc}")

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        index = int(getattr(event, "index", -1))
        if index < 0 or index >= len(self._current_items):
            return
        try:
            await self._load_item_detail(self._current_items[index])
        except Exception as exc:
            self._show_error(f"Failed to load item details.\n{exc}")

    async def _refresh_libraries(self) -> None:
        try:
            await self._load_libraries()
        except Exception as exc:
            self._set_items([])
            self._show_error(f"Failed to load Zotero data.\n{exc}")

    async def _load_libraries(self) -> None:
        self._libraries = await self._service.list_library_tree()
        tree = cast(Tree[NavigationTarget], self.query_one("#libraries-tree", Tree))
        tree.clear()
        tree.root.expand()

        first_target_node = None
        for library in self._libraries:
            node = tree.root.add(
                library.library.name,
                data=NavigationTarget(library=library.library),
                expand=True,
            )
            if first_target_node is None:
                first_target_node = node
            collection_tree = self._collection_tree(library.collections)
            for collection in collection_tree.get(None, []):
                self._attach_collection_node(
                    parent=node,
                    library=library.library,
                    collection=collection,
                    collection_tree=collection_tree,
                )

        if first_target_node is not None:
            tree.select_node(first_target_node)
            await self._load_items(first_target_node.data)
            tree.focus()
        else:
            self._set_items([])
            self.query_one("#detail-content", Static).update("No libraries available.")

    async def _load_items(self, target: NavigationTarget | None) -> None:
        if target is None:
            return

        self._active_library = target.library
        self._loaded_detail_key = None
        self.sub_title = f"{target.library.name}"
        items = await self._service.list_items(target.library, collection_key=target.collection_key)
        self._set_items(items)

        if items:
            self.query_one("#items-list", OptionList).highlighted = 0
            await self._load_item_detail(items[0])
        else:
            detail = self.query_one("#detail-content", Static)
            detail.update("No items in this view.")

    async def _load_item_detail(self, item: Item) -> None:
        if self._active_library is None:
            return

        detail_key = (self._active_library.api_path, item.key)
        if detail_key == self._loaded_detail_key:
            return

        self._loaded_detail_key = detail_key
        detail = self.query_one("#detail-content", Static)
        detail.update("Loading item details...")
        snapshot = await self._service.get_item_snapshot(self._active_library, item.key)
        detail.update(self._render_snapshot(snapshot))

    def _set_items(self, items: list[Item]) -> None:
        self._current_items = items
        option_list = self.query_one("#items-list", OptionList)
        option_list.clear_options()
        option_list.add_options([self._format_item_label(item) for item in items])

    def _attach_collection_node(
        self,
        parent: Any,
        library: LibraryHandle,
        collection: Collection,
        collection_tree: dict[str | None, list[Collection]],
    ) -> None:
        node = parent.add(
            self._format_collection_label(collection),
            data=NavigationTarget(library=library, collection_key=collection.key),
            expand=False,
        )
        for child in collection_tree.get(collection.key, []):
            self._attach_collection_node(
                parent=node,
                library=library,
                collection=child,
                collection_tree=collection_tree,
            )

    def _collection_tree(
        self,
        collections: list[Collection],
    ) -> dict[str | None, list[Collection]]:
        grouped: dict[str | None, list[Collection]] = defaultdict(list)
        for collection in collections:
            grouped[collection.data.parent_key()].append(collection)
        for siblings in grouped.values():
            siblings.sort(key=lambda collection: collection.data.name.casefold())
        return grouped

    def _format_collection_label(self, collection: Collection) -> str:
        return f"{collection.data.name} ({collection.meta.numItems})"

    def _format_item_label(self, item: Item) -> str:
        year = f" [{item.year}]" if item.year else ""
        return f"{item.title}{year}"

    def _render_snapshot(self, snapshot: ItemSnapshot) -> Group:
        item = snapshot.item
        collection_names = self._resolve_collection_names(item.data.collections)
        tag_names = ", ".join(tag.tag for tag in item.data.tags) or None
        lines: list[Text | Rule] = [
            Text(item.title, style="bold #f5f1e8"),
            Text(item.author_summary, style="#d4c6a3"),
            Text(
                " | ".join(
                    value
                    for value in (
                        item.data.itemType,
                        item.year,
                        item.publication,
                    )
                    if value
                ),
                style="#98a4b8",
            ),
            Rule(style="#3d4552"),
        ]

        metadata = [
            ("DOI", item.data.DOI),
            ("URL", item.data.url),
            ("Collections", collection_names),
            ("Tags", tag_names),
            ("Date Added", item.data.dateAdded),
            ("Date Modified", item.data.dateModified),
        ]
        for label, value in metadata:
            if value:
                lines.append(Text(f"{label}: {value}", style="#c8d0dd"))

        attachments = ", ".join(child.attachment_label for child in snapshot.attachments) or "None"
        lines.extend(
            [
                Rule(style="#3d4552"),
                Text(f"Attachments: {attachments}", style="#c8d0dd"),
            ]
        )

        if snapshot.notes:
            lines.append(Text("Notes", style="bold #f5f1e8"))
            for note in snapshot.notes:
                lines.append(Text(f"- {note.note_text or note.title}", style="#c8d0dd"))

        abstract = item.abstract_text
        if abstract:
            lines.extend(
                [
                    Rule(style="#3d4552"),
                    Text("Abstract", style="bold #f5f1e8"),
                    Text(abstract, style="#e8e6df"),
                ]
            )

        return Group(*lines)

    def _resolve_collection_names(self, keys: list[str]) -> str | None:
        if not keys or self._active_library is None:
            return None

        collection_names: dict[str, str] = {}
        for tree in self._libraries:
            if tree.library == self._active_library:
                collection_names = {
                    collection.key: collection.data.name for collection in tree.collections
                }
                break

        resolved = [collection_names.get(key, key) for key in keys]
        return ", ".join(resolved) if resolved else None

    def _show_error(self, message: str) -> None:
        self.query_one("#detail-content", Static).update(message)
