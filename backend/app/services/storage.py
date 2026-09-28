"""Storage keys are private. Parsers use a materialized local file.

An object backend can implement local_path as a managed download/cache; routers
never concatenate client filenames or expose storage paths.
"""
from pathlib import Path
from typing import Protocol
import secrets
from app.config import settings


class StorageBackend(Protocol):
    def local_path(self, key: str) -> Path: ...
    def new_key(self, temporary: bool = False) -> str: ...
    def delete(self, key: str) -> None: ...
    def promote(self, source_key: str, destination_key: str) -> None: ...


class LocalStorageBackend:
    @property
    def root(self):
        root = settings.upload_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def local_path(self, key: str) -> Path:
        if not key or "/" in key or "\\" in key or ":" in key or key in {".", ".."}:
            raise ValueError("Invalid storage key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def new_key(self, temporary=False):
        return (".tmp_" if temporary else "") + secrets.token_hex(16) + ".xlsx"

    def delete(self, key):
        self.local_path(key).unlink(missing_ok=True)

    def promote(self, source_key, destination_key):
        self.local_path(source_key).replace(self.local_path(destination_key))


storage: StorageBackend = LocalStorageBackend()
