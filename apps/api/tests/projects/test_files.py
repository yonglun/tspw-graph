from io import BytesIO

import pytest

from app.projects.files import InvalidUpload, UploadStore


def test_save_normalizes_gb18030_and_uses_server_filename(tmp_path):
    store = UploadStore(tmp_path, max_bytes=1024)
    result = store.save(
        "project-1", "../原稿.txt", BytesIO("第一章 开端".encode("gb18030"))
    )
    assert result.encoding == "gb18030"
    assert result.path.parent == tmp_path / "project-1"
    assert result.path.name == "source.txt"
    assert result.path.read_text(encoding="utf-8") == "第一章 开端"


def test_save_rejects_non_txt_and_oversized_content(tmp_path):
    store = UploadStore(tmp_path, max_bytes=4)
    with pytest.raises(InvalidUpload, match="TXT_ONLY"):
        store.save("p", "book.pdf", BytesIO(b"text"))
    with pytest.raises(InvalidUpload, match="FILE_TOO_LARGE"):
        store.save("p", "book.txt", BytesIO(b"12345"))


def test_save_rejects_empty_invalid_encoding_and_unsafe_project_id(tmp_path):
    store = UploadStore(tmp_path, max_bytes=1024)
    with pytest.raises(InvalidUpload, match="EMPTY_FILE"):
        store.save("p", "book.txt", BytesIO(b""))
    with pytest.raises(InvalidUpload, match="UNSUPPORTED_ENCODING"):
        store.save("p", "book.txt", BytesIO(b"\x81"))
    with pytest.raises(InvalidUpload, match="INVALID_PROJECT_PATH"):
        store.save("../escape", "book.txt", BytesIO(b"text"))
