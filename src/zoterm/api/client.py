from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from zoterm.api.models import Collection, Item
from zoterm.config import Settings

ModelT = TypeVar("ModelT", bound=BaseModel)


class ZoteroApiError(RuntimeError):
    """Raised when the Zotero local API returns an error."""


class ZoteroClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=self._settings.api_base_url.rstrip("/"),
            headers={"Zotero-API-Version": "3"},
            timeout=self._settings.request_timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        query: dict[str, Any] = {"format": "json"}
        if params:
            query.update(params)

        response = await self._client.get(path, params=query)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ZoteroApiError(f"Zotero API request failed for {path}: {exc}") from exc
        return response

    async def get_json(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        response = await self._request(path, params=params)
        return response.json()

    async def _get_paginated(
        self,
        path: str,
        model: type[ModelT],
        *,
        params: Mapping[str, Any] | None = None,
    ) -> list[ModelT]:
        query = dict(params or {})
        limit = int(query.pop("limit", self._settings.page_size))
        start = int(query.pop("start", 0))
        results: list[ModelT] = []

        while True:
            response = await self._request(path, params={**query, "limit": limit, "start": start})
            payload = response.json()
            if not isinstance(payload, list):
                raise ZoteroApiError(f"Expected a list payload for {path}, got {type(payload)!r}")

            batch = [model.model_validate(item) for item in payload]
            results.extend(batch)

            total_results = response.headers.get("Total-Results")
            if total_results is not None and len(results) >= int(total_results):
                break
            if len(batch) < limit or not batch:
                break

            start += limit

        return results

    async def get_collections(self, library_path: str) -> list[Collection]:
        return await self._get_paginated(f"{library_path}/collections", Collection)

    async def get_top_items(
        self,
        library_path: str,
        *,
        collection_key: str | None = None,
    ) -> list[Item]:
        if collection_key:
            path = f"{library_path}/collections/{collection_key}/items/top"
        else:
            path = f"{library_path}/items/top"
        return await self._get_paginated(path, Item)

    async def get_items_sample(self, library_path: str, *, limit: int = 1) -> list[Item]:
        return await self._get_paginated(f"{library_path}/items/top", Item, params={"limit": limit})

    async def get_item(self, library_path: str, item_key: str) -> Item:
        payload = await self.get_json(f"{library_path}/items/{item_key}")
        return Item.model_validate(payload)

    async def get_children(self, library_path: str, item_key: str) -> list[Item]:
        return await self._get_paginated(f"{library_path}/items/{item_key}/children", Item)

    async def get_groups(self) -> list[Any]:
        payload = await self.get_json("/users/0/groups")
        return payload if isinstance(payload, list) else []
