import os
from pathlib import Path
from typing import Protocol

from app.config import Settings


class Storage(Protocol):
    def save(self, doc_id: str, ext: str, data: bytes) -> str: ...
    def delete(self, path: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, doc_id, ext, data):
        path = self.root / f"{doc_id}{ext}"  # never use the client-supplied filename on disk
        path.write_bytes(data)
        return str(path)

    def delete(self, path):
        if path:
            Path(path).unlink(missing_ok=True)


class GCSStorage:
    def __init__(self, bucket: str):
        from google.cloud import storage

        self.bucket_name = bucket
        self.bucket = storage.Client().bucket(bucket)

    def save(self, doc_id, ext, data):
        self.bucket.blob(f"uploads/{doc_id}{ext}").upload_from_string(data)
        return f"gs://{self.bucket_name}/uploads/{doc_id}{ext}"

    def delete(self, path):
        prefix = f"gs://{self.bucket_name}/"
        if path.startswith(prefix):
            self.bucket.blob(path[len(prefix):]).delete()


def build_storage(s: Settings) -> Storage:
    return GCSStorage(s.gcs_bucket) if s.storage_backend == "gcs" else LocalStorage(s.upload_dir)
