from zoterm.api.models import Item


def test_note_item_uses_note_text_as_title() -> None:
    item = Item.model_validate(
        {
            "key": "NOTE1",
            "version": 1,
            "library": {"type": "user", "id": 1, "name": "My Library"},
            "data": {
                "key": "NOTE1",
                "version": 1,
                "itemType": "note",
                "note": "<p>Important comment</p>",
            },
        }
    )

    assert item.title == "Important comment"
