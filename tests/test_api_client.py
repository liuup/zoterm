from __future__ import annotations

import httpx
import pytest
import respx

from zoterm.api.client import ZoteroClient
from zoterm.config import Settings


@pytest.mark.asyncio
@respx.mock
async def test_get_top_items_paginates_across_total_results() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        if start == 0:
            return httpx.Response(
                200,
                headers={"Total-Results": "3"},
                json=[
                    {
                        "key": "A1",
                        "version": 1,
                        "library": {"type": "user", "id": 1, "name": "My Library"},
                        "meta": {"creatorSummary": "One", "parsedDate": "2024-01-01"},
                        "data": {
                            "key": "A1",
                            "version": 1,
                            "itemType": "journalArticle",
                            "title": "One",
                        },
                    },
                    {
                        "key": "A2",
                        "version": 1,
                        "library": {"type": "user", "id": 1, "name": "My Library"},
                        "meta": {"creatorSummary": "Two", "parsedDate": "2024-01-02"},
                        "data": {
                            "key": "A2",
                            "version": 1,
                            "itemType": "journalArticle",
                            "title": "Two",
                        },
                    },
                ],
            )

        return httpx.Response(
            200,
            headers={"Total-Results": "3"},
            json=[
                {
                    "key": "A3",
                    "version": 1,
                    "library": {"type": "user", "id": 1, "name": "My Library"},
                    "meta": {"creatorSummary": "Three", "parsedDate": "2024-01-03"},
                    "data": {
                        "key": "A3",
                        "version": 1,
                        "itemType": "journalArticle",
                        "title": "Three",
                    },
                }
            ],
        )

    route = respx.get("http://localhost:23119/api/users/0/items/top").mock(side_effect=responder)

    client = ZoteroClient(Settings(api_base_url="http://localhost:23119/api", page_size=2))
    try:
        items = await client.get_top_items("/users/0")
    finally:
        await client.aclose()

    assert route.call_count == 2
    assert [item.title for item in items] == ["One", "Two", "Three"]
