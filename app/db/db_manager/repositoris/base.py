from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Generic, TypeVar

M = TypeVar("M")  # Generic model type


class Repository(ABC, Generic[M]):
    """
    Abstract repository interface for CRUD operations.
    """

    @abstractmethod
    async def create(self, obj_data: dict) -> M:
        pass

    @abstractmethod
    async def get(self, obj_id: int) -> M | None:
        pass

    @abstractmethod
    async def get_all(self) -> Sequence[M]:
        pass

    @abstractmethod
    async def update(self, obj_id: int, obj_data: dict) -> M | None:
        pass

    @abstractmethod
    async def delete(self, obj_id: int) -> bool:
        pass
