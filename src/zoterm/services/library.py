from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zoterm.api.client import ZoteroClient
from zoterm.api.models import Collection, Item


@dataclass(frozen=True)
class LibraryHandle:
    name: str
    api_path: str
    kind: str
    library_id: int


@dataclass(frozen=True)
class LibraryTree:
    library: LibraryHandle
    collections: list[Collection]


@dataclass(frozen=True)
class ItemSnapshot:
    item: Item
    attachments: list[Item]
    notes: list[Item]


class LibraryService:
    def __init__(self, client: ZoteroClient) -> None:
        self._client = client

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_library_tree(self) -> list[LibraryTree]:
        user_collections = await self._client.get_collections("/users/0")
        user_name = await self._resolve_user_library_name(user_collections)
        trees = [
            LibraryTree(
                library=LibraryHandle(
                    name=user_name,
                    api_path="/users/0",
                    kind="user",
                    library_id=0,
                ),
                collections=self._sort_collections(user_collections),
            )
        ]

        for group in await self._discover_group_libraries():
            collections = await self._client.get_collections(group.api_path)
            trees.append(
                LibraryTree(
                    library=group,
                    collections=self._sort_collections(collections),
                )
            )

        return trees

    async def list_items(
        self,
        library: LibraryHandle,
        *,
        collection_key: str | None = None,
    ) -> list[Item]:
        return await self._client.get_top_items(library.api_path, collection_key=collection_key)

    async def get_item_snapshot(self, library: LibraryHandle, item_key: str) -> ItemSnapshot:
        item = await self._client.get_item(library.api_path, item_key)
        children = await self._client.get_children(library.api_path, item_key)
        attachments = [child for child in children if child.is_attachment]
        notes = [child for child in children if child.is_note]
        return ItemSnapshot(item=item, attachments=attachments, notes=notes)

    async def _resolve_user_library_name(self, collections: list[Collection]) -> str:
        if collections:
            return collections[0].library.name

        sample_items = await self._client.get_items_sample("/users/0")
        if sample_items:
            return sample_items[0].library.name

        return "My Library"

    async def _discover_group_libraries(self) -> list[LibraryHandle]:
        groups = await self._client.get_groups()
        libraries: list[LibraryHandle] = []

        for raw_group in groups:
            group_id, group_name = await self._extract_group_identity(raw_group)
            if group_id is None or group_name is None:
                continue
            libraries.append(
                LibraryHandle(
                    name=group_name,
                    api_path=f"/groups/{group_id}",
                    kind="group",
                    library_id=group_id,
                )
            )

        return libraries

    async def _extract_group_identity(self, payload: Any) -> tuple[int | None, str | None]:
        if isinstance(payload, int):
            details = await self._client.get_json(f"/groups/{payload}")
            return self._extract_group_identity_from_mapping(details)

        if isinstance(payload, dict):
            group_id, group_name = self._extract_group_identity_from_mapping(payload)
            if group_id is not None and group_name is not None:
                return group_id, group_name
            if group_id is not None:
                details = await self._client.get_json(f"/groups/{group_id}")
                return self._extract_group_identity_from_mapping(details)

        return None, None

    def _extract_group_identity_from_mapping(
        self,
        payload: dict[str, Any],
    ) -> tuple[int | None, str | None]:
        data = payload.get("data")
        if isinstance(data, dict):
            group_id = data.get("id") or payload.get("id")
            group_name = data.get("name") or payload.get("name")
        else:
            group_id = payload.get("id")
            group_name = payload.get("name")

        if isinstance(group_id, int):
            return group_id, group_name if isinstance(group_name, str) else None
        return None, None

    def _sort_collections(self, collections: list[Collection]) -> list[Collection]:
        return sorted(collections, key=lambda collection: collection.data.name.casefold())
