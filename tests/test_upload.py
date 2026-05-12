import io
import pytest
from fastapi.testclient import TestClient


def _txt_file(name: str, content: str = "hello world " * 100):
    return (name, io.BytesIO(content.encode()), "text/plain")


def test_upload_txt_success(client: TestClient):
    resp = client.post("/api/upload", files=[("files", _txt_file("test.txt"))])
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["documents"]) == 1
    assert data["documents"][0]["document_name"] == "test.txt"
    assert data["documents"][0]["chunk_count"] >= 1


def test_upload_unsupported_extension(client: TestClient):
    resp = client.post("/api/upload", files=[("files", ("bad.exe", io.BytesIO(b"data"), "application/octet-stream"))])
    assert resp.status_code == 415


def test_upload_too_large(client: TestClient):
    big = b"x" * (11 * 1024 * 1024)
    resp = client.post("/api/upload", files=[("files", ("big.txt", io.BytesIO(big), "text/plain"))])
    assert resp.status_code == 413


def test_documents_list_empty(client: TestClient):
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_documents_list_after_upload(client: TestClient):
    client.post("/api/upload", files=[("files", _txt_file("doc.txt", "abc " * 500))])
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert any(d["document_name"] == "doc.txt" for d in docs)
