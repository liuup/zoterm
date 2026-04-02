from __future__ import annotations

import html
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_YEAR_PATTERN = re.compile(r"\b(\d{4})\b")
_HTML_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _to_plain_text(value: str | None) -> str:
    if not value:
        return ""
    stripped = _HTML_PATTERN.sub(" ", value)
    unescaped = html.unescape(stripped)
    return _WHITESPACE_PATTERN.sub(" ", unescaped).strip()


class LibraryRef(BaseModel):
    type: str
    id: int
    name: str


class Creator(BaseModel):
    firstName: str | None = None
    lastName: str | None = None
    name: str | None = None
    creatorType: str | None = None

    @property
    def full_name(self) -> str:
        if self.name:
            return self.name
        parts = [part for part in (self.firstName, self.lastName) if part]
        return " ".join(parts)


class Tag(BaseModel):
    tag: str
    type: int | None = None


class CollectionMeta(BaseModel):
    numCollections: int = 0
    numItems: int = 0


class CollectionData(BaseModel):
    key: str
    version: int
    name: str
    parentCollection: str | bool | None = None
    relations: dict[str, Any] = Field(default_factory=dict)

    def parent_key(self) -> str | None:
        return self.parentCollection if isinstance(self.parentCollection, str) else None


class Collection(BaseModel):
    key: str
    version: int
    library: LibraryRef
    meta: CollectionMeta = Field(default_factory=CollectionMeta)
    data: CollectionData


class ItemMeta(BaseModel):
    creatorSummary: str | None = None
    parsedDate: str | None = None
    numChildren: int | None = 0


class ItemData(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    version: int
    itemType: str
    title: str | None = None
    abstractNote: str | None = None
    date: str | None = None
    url: str | None = None
    DOI: str | None = None
    accessDate: str | None = None
    libraryCatalog: str | None = None
    publicationTitle: str | None = None
    proceedingsTitle: str | None = None
    conferenceName: str | None = None
    repository: str | None = None
    archive: str | None = None
    archiveID: str | None = None
    publisher: str | None = None
    place: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    bookTitle: str | None = None
    seriesTitle: str | None = None
    journalAbbreviation: str | None = None
    extra: str | None = None
    note: str | None = None
    parentItem: str | None = None
    linkMode: str | None = None
    contentType: str | None = None
    filename: str | None = None
    charset: str | None = None
    mtime: int | None = None
    md5: str | None = None
    dateAdded: str | None = None
    dateModified: str | None = None
    creators: list[Creator] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)


class Item(BaseModel):
    key: str
    version: int
    library: LibraryRef
    meta: ItemMeta = Field(default_factory=ItemMeta)
    data: ItemData
    links: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @property
    def is_attachment(self) -> bool:
        return self.data.itemType == "attachment"

    @property
    def is_note(self) -> bool:
        return self.data.itemType == "note"

    @property
    def is_regular_item(self) -> bool:
        return not self.is_attachment and not self.is_note

    @property
    def title(self) -> str:
        if self.data.title:
            return self.data.title
        if self.is_note:
            plain_note = _to_plain_text(self.data.note)
            if plain_note:
                return plain_note.splitlines()[0][:80]
            return "Untitled note"
        if self.data.filename:
            return self.data.filename
        return "Untitled item"

    @property
    def year(self) -> str | None:
        for candidate in (self.meta.parsedDate, self.data.date):
            if not candidate:
                continue
            match = _YEAR_PATTERN.search(candidate)
            if match:
                return match.group(1)
        return None

    @property
    def author_names(self) -> list[str]:
        names = [creator.full_name for creator in self.data.creators if creator.full_name]
        return names

    @property
    def author_summary(self) -> str:
        if self.meta.creatorSummary:
            return self.meta.creatorSummary
        names = self.author_names
        if not names:
            return "Unknown author"
        if len(names) <= 3:
            return ", ".join(names)
        return f"{names[0]} et al."

    @property
    def abstract_text(self) -> str:
        return _to_plain_text(self.data.abstractNote)

    @property
    def note_text(self) -> str:
        return _to_plain_text(self.data.note)

    @property
    def publication(self) -> str | None:
        for field in (
            self.data.publicationTitle,
            self.data.proceedingsTitle,
            self.data.bookTitle,
            self.data.repository,
            self.data.publisher,
            self.data.libraryCatalog,
        ):
            if field:
                return field
        return None

    @property
    def attachment_label(self) -> str:
        if self.data.filename:
            return self.data.filename
        return self.title
