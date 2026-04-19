"""Sample Python fixture for tree-sitter query validation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Optional, Protocol

# Type alias
type Vector = list[float]


class DbProtocol(Protocol):
    async def query(self, sql: str, *args: object) -> dict: ...

    def execute(self, sql: str, *args: object) -> None: ...


class Animal:
    """Base class for animals."""

    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    def speak(self) -> str:
        return "..."

    @staticmethod
    def kingdom() -> str:
        return "Animalia"


class Dog(Animal):
    """A dog."""

    def speak(self) -> str:
        return f"Woof, I am {self.name}"


def greet(name: str, greeting: str = "Hello") -> str:
    return f"{greeting}, {name}!"


async def fetch_data() -> bytes:
    async with asyncio.timeout(30):
        await asyncio.sleep(0)
        return b""


def apply(func: Callable[[int], int], value: int) -> int:
    return func(value)


class Repository:
    def __init__(self, db: DbProtocol) -> None:
        self.db = db

    async def find_by_id(self, record_id: int) -> Optional[dict]:
        result = await self.db.query("SELECT * FROM records WHERE id = $1", record_id)
        return result

    def save(self, record: dict) -> None:
        self.db.execute("INSERT INTO records VALUES ($1)", record)


def process(items: list[int]) -> list[int]:
    _ = apply(lambda x: x * 2, 10)
    return [x for x in items if x > 0]
