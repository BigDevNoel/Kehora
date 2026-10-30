import uuid

import httpx
import pytest

from kehora_common.settings import get_settings
from kehora_common.storage import Storage

pytestmark = pytest.mark.s3


@pytest.fixture(scope="module")
def storage() -> Storage:
    s = Storage(get_settings().model_copy(update={"s3_bucket": "kehora-test"}))
    s.ensure_bucket()
    return s


def test_put_records_hash_and_size(storage: Storage) -> None:
    obj = storage.put_bytes(f"t/{uuid.uuid4()}.txt", b"hello", "text/plain")
    assert obj.size == 5
    assert obj.sha256 == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert storage.get_bytes(obj.key) == b"hello"


def test_signed_get_url_downloads_and_expires_in_ten_minutes(storage: Storage) -> None:
    obj = storage.put_bytes(f"t/{uuid.uuid4()}.txt", b"signed", "text/plain")
    url = storage.presign_get(obj.key)
    assert "X-Amz-Expires=600" in url
    assert httpx.get(url).content == b"signed"


def test_tampered_signed_url_is_rejected(storage: Storage) -> None:
    obj = storage.put_bytes(f"t/{uuid.uuid4()}.txt", b"secret", "text/plain")
    url = storage.presign_get(obj.key).replace(obj.key, obj.key + "x")
    assert httpx.get(url).status_code == 403


def test_signed_put_url_uploads(storage: Storage) -> None:
    key = f"uploads/{uuid.uuid4()}.png"
    url = storage.presign_put(key, "image/png")
    resp = httpx.put(url, content=b"\x89PNG", headers={"Content-Type": "image/png"})
    assert resp.status_code == 200
    assert storage.get_bytes(key) == b"\x89PNG"
