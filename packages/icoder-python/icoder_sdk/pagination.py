"""Lazy, bounded cursor pagination helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Generic, Optional, TypeVar


PageT = TypeVar("PageT")
ItemT = TypeVar("ItemT")


class CursorPager(Generic[PageT, ItemT]):
    """Iterate cursor pages lazily and fail closed on cursor loops."""

    def __init__(
        self,
        fetch_page: Callable[[Optional[str]], PageT],
        items: Callable[[PageT], Iterable[ItemT]],
        next_page_token: Callable[[PageT], Optional[str]],
        *,
        initial_page_token: Optional[str] = None,
        max_pages: int = 10000,
    ) -> None:
        if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")
        self._fetch_page = fetch_page
        self._items = items
        self._next_page_token = next_page_token
        self._initial_page_token = initial_page_token
        self._max_pages = max_pages

    def pages(self) -> Iterator[PageT]:
        token = self._initial_page_token
        seen = {token} if token else set()
        for _ in range(self._max_pages):
            page = self._fetch_page(token)
            yield page
            raw_next_token = self._next_page_token(page)
            if raw_next_token is None or raw_next_token == "":
                return
            if not isinstance(raw_next_token, str):
                raise RuntimeError("iCoDer pagination returned an invalid page token")
            next_token = raw_next_token
            if next_token in seen:
                raise RuntimeError("iCoDer pagination returned a repeated page token")
            seen.add(next_token)
            token = next_token
        raise RuntimeError(f"iCoDer pagination exceeded max_pages={self._max_pages}")

    def __iter__(self) -> Iterator[ItemT]:
        for page in self.pages():
            yield from self._items(page)


class PageNumberPager(Generic[PageT, ItemT]):
    """Lazily iterate page-number results using an authoritative total count."""

    def __init__(
        self,
        fetch_page: Callable[[int], PageT],
        items: Callable[[PageT], Iterable[ItemT]],
        total_items: Callable[[PageT], int],
        *,
        initial_page: int = 1,
        max_pages: int = 10000,
    ) -> None:
        if not isinstance(initial_page, int) or isinstance(initial_page, bool) or initial_page < 1:
            raise ValueError("initial_page must be a positive integer")
        if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")
        self._fetch_page = fetch_page
        self._items = items
        self._total_items = total_items
        self._initial_page = initial_page
        self._max_pages = max_pages

    def pages(self) -> Iterator[PageT]:
        emitted = 0
        for index in range(self._max_pages):
            page = self._fetch_page(self._initial_page + index)
            page_items = tuple(self._items(page))
            total = self._total_items(page)
            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                raise RuntimeError("iCoDer pagination returned an invalid total")
            yield page
            emitted += len(page_items)
            if not page_items or emitted >= total:
                return
        raise RuntimeError(f"iCoDer pagination exceeded max_pages={self._max_pages}")

    def __iter__(self) -> Iterator[ItemT]:
        for page in self.pages():
            yield from self._items(page)
