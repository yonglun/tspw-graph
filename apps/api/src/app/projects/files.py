from dataclasses import dataclass
import hashlib
from io import BufferedIOBase
from pathlib import Path
import re
import shutil
from typing import BinaryIO


class InvalidUpload(ValueError):
    pass


@dataclass(frozen=True)
class StoredUpload:
    path: Path
    encoding: str
    size_bytes: int
    sha256: str


def decode_text(raw: bytes) -> tuple[str, str]:
    for codec, label in (
        ("utf-8-sig", "utf-8-bom"),
        ("utf-8", "utf-8"),
        ("gb18030", "gb18030"),
    ):
        try:
            return raw.decode(codec), label
        except UnicodeDecodeError:
            continue
    raise InvalidUpload("UNSUPPORTED_ENCODING")


class UploadStore:
    _PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")

    def __init__(self, root: Path, max_bytes: int = 20 * 1024 * 1024) -> None:
        self.root = root.resolve()
        self.max_bytes = max_bytes

    def project_dir(self, project_id: str) -> Path:
        if not self._PROJECT_ID.fullmatch(project_id):
            raise InvalidUpload("INVALID_PROJECT_PATH")
        directory = (self.root / project_id).resolve()
        if self.root not in directory.parents:
            raise InvalidUpload("INVALID_PROJECT_PATH")
        return directory

    def save(self, project_id: str, filename: str, stream: BinaryIO) -> StoredUpload:
        if Path(filename).suffix.lower() != ".txt":
            raise InvalidUpload("TXT_ONLY")
        raw = stream.read(self.max_bytes + 1)
        if len(raw) > self.max_bytes:
            raise InvalidUpload("FILE_TOO_LARGE")
        if not raw:
            raise InvalidUpload("EMPTY_FILE")

        text, encoding = decode_text(raw)
        directory = self.project_dir(project_id)
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / "source.txt"
        path.write_text(text, encoding="utf-8")
        return StoredUpload(
            path=path,
            encoding=encoding,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    def delete_project(self, project_id: str) -> None:
        directory = self.project_dir(project_id)
        if directory.exists():
            shutil.rmtree(directory)
