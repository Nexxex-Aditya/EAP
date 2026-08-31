"""Abstract storage adapter interface.

Handles persistence of artifacts (workbooks, screenshots, exports, etc.)
to an S3-compatible object store or local filesystem.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageAdapter(ABC):
    """Abstract interface for artifact storage."""

    @abstractmethod
    async def upload(self, local_path: str | Path, remote_key: str) -> str:
        """Upload a local file to storage. Returns the remote URI."""

    @abstractmethod
    async def download(self, remote_key: str, local_path: str | Path) -> str:
        """Download a file from storage. Returns the local path."""

    @abstractmethod
    async def exists(self, remote_key: str) -> bool:
        """Check if a remote key exists."""

    @abstractmethod
    async def list_keys(self, prefix: str) -> list[str]:
        """List all keys under a prefix."""

    @abstractmethod
    async def delete(self, remote_key: str) -> None:
        """Delete a remote object."""

    @abstractmethod
    async def get_url(self, remote_key: str, *, expires_in: int = 3600) -> str:
        """Generate a pre-signed URL for a remote object."""
