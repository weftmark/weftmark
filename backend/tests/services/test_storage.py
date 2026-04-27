"""
Tests for app.services.storage.

All filesystem operations are redirected to pytest's tmp_path so no real
upload directory is touched.  The module-level `settings` object is patched
before each test via a session-scoped monkeypatch on the upload_dir attribute.
"""

import uuid

import pytest

import app.services.storage as storage

# ---------------------------------------------------------------------------
# Fixture: redirect every storage call to tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _use_tmp_upload_dir(tmp_path, monkeypatch):
    """Point storage.settings.upload_dir at a fresh temp directory."""
    monkeypatch.setattr(storage.settings, "upload_dir", str(tmp_path))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# save_wif / read_wif
# ---------------------------------------------------------------------------


class TestSaveReadWif:
    def test_save_returns_relative_path(self):
        pid = _pid()
        rel = storage.save_wif(pid, "test.wif", b"WIF DATA")
        assert not rel.startswith("/")

    def test_round_trip(self):
        pid = _pid()
        data = b"[WIF]\nVersion=1.1"
        rel = storage.save_wif(pid, "test.wif", data)
        assert storage.read_wif(rel) == data

    def test_overwrite(self):
        pid = _pid()
        storage.save_wif(pid, "test.wif", b"v1")
        rel = storage.save_wif(pid, "test.wif", b"v2")
        assert storage.read_wif(rel) == b"v2"

    def test_saved_as_original_wif(self):
        pid = _pid()
        rel = storage.save_wif(pid, "anything.wif", b"data")
        assert rel.endswith("original.wif")


# ---------------------------------------------------------------------------
# save_preview / read_preview / preview_exists
# ---------------------------------------------------------------------------


class TestPreview:
    def test_save_returns_relative_path(self):
        rel = storage.save_preview(_pid(), b"\x89PNG")
        assert not rel.startswith("/")

    def test_round_trip(self):
        pid = _pid()
        data = b"\x89PNG\r\n\x1a\n"
        rel = storage.save_preview(pid, data)
        assert storage.read_preview(rel) == data

    def test_preview_exists_true(self):
        pid = _pid()
        rel = storage.save_preview(pid, b"img")
        assert storage.preview_exists(rel) is True

    def test_preview_exists_false_for_unknown_path(self):
        assert storage.preview_exists("projects/nonexistent/preview.png") is False

    def test_preview_exists_false_for_none(self):
        assert storage.preview_exists(None) is False

    def test_preview_exists_false_for_empty_string(self):
        assert storage.preview_exists("") is False


# ---------------------------------------------------------------------------
# Loom profile photo
# ---------------------------------------------------------------------------


class TestLoomPhoto:
    def test_save_returns_relative_path(self):
        rel = storage.save_loom_photo(_pid(), ".jpg", b"JPEG")
        assert not rel.startswith("/")

    def test_round_trip_via_read_file(self):
        lid = _pid()
        data = b"JPEG DATA"
        rel = storage.save_loom_photo(lid, ".jpg", data)
        assert storage.read_file(rel) == data

    def test_extension_preserved(self):
        rel = storage.save_loom_photo(_pid(), ".png", b"PNG")
        assert rel.endswith(".png")

    def test_delete_removes_file(self):
        lid = _pid()
        rel = storage.save_loom_photo(lid, ".jpg", b"data")
        storage.delete_loom_photo(rel)
        assert storage.file_exists(rel) is False

    def test_delete_nonexistent_is_silent(self):
        storage.delete_loom_photo("looms/nonexistent/profile.jpg")


# ---------------------------------------------------------------------------
# Loom version photos
# ---------------------------------------------------------------------------


class TestVersionPhoto:
    def test_save_returns_relative_path(self):
        rel = storage.save_version_photo(_pid(), _pid(), _pid(), ".jpg", b"data")
        assert not rel.startswith("/")

    def test_round_trip(self):
        lid, vid, phid = _pid(), _pid(), _pid()
        data = b"PHOTO BYTES"
        rel = storage.save_version_photo(lid, vid, phid, ".jpg", data)
        assert storage.read_file(rel) == data

    def test_delete_removes_file(self):
        lid, vid, phid = _pid(), _pid(), _pid()
        rel = storage.save_version_photo(lid, vid, phid, ".jpg", b"data")
        storage.delete_version_photo(rel)
        assert storage.file_exists(rel) is False

    def test_delete_nonexistent_is_silent(self):
        storage.delete_version_photo("looms/x/versions/y/photos/z.jpg")

    def test_multiple_photos_same_version(self):
        lid, vid = _pid(), _pid()
        ph1, ph2 = _pid(), _pid()
        rel1 = storage.save_version_photo(lid, vid, ph1, ".jpg", b"a")
        rel2 = storage.save_version_photo(lid, vid, ph2, ".jpg", b"b")
        assert rel1 != rel2
        assert storage.read_file(rel1) == b"a"
        assert storage.read_file(rel2) == b"b"


# ---------------------------------------------------------------------------
# Loom version receipts
# ---------------------------------------------------------------------------


class TestVersionReceipt:
    def test_save_returns_relative_path(self):
        rel = storage.save_version_receipt(_pid(), _pid(), _pid(), ".pdf", b"PDF")
        assert not rel.startswith("/")

    def test_round_trip(self):
        lid, vid, rid = _pid(), _pid(), _pid()
        data = b"RECEIPT DATA"
        rel = storage.save_version_receipt(lid, vid, rid, ".pdf", data)
        assert storage.read_file(rel) == data

    def test_delete_removes_file(self):
        lid, vid, rid = _pid(), _pid(), _pid()
        rel = storage.save_version_receipt(lid, vid, rid, ".pdf", b"data")
        storage.delete_version_receipt(rel)
        assert storage.file_exists(rel) is False

    def test_delete_nonexistent_is_silent(self):
        storage.delete_version_receipt("looms/x/versions/y/receipts/z.pdf")


# ---------------------------------------------------------------------------
# Yarn photo
# ---------------------------------------------------------------------------


class TestYarnPhoto:
    def test_save_returns_relative_path(self):
        rel = storage.save_yarn_photo(_pid(), ".jpg", b"YARN IMG")
        assert not rel.startswith("/")

    def test_round_trip(self):
        yid = _pid()
        data = b"YARN PHOTO"
        rel = storage.save_yarn_photo(yid, ".jpg", data)
        assert storage.read_file(rel) == data

    def test_extension_preserved(self):
        rel = storage.save_yarn_photo(_pid(), ".png", b"data")
        assert rel.endswith(".png")

    def test_delete_removes_file(self):
        yid = _pid()
        rel = storage.save_yarn_photo(yid, ".jpg", b"data")
        storage.delete_yarn_photo(rel)
        assert storage.file_exists(rel) is False

    def test_delete_nonexistent_is_silent(self):
        storage.delete_yarn_photo("yarn/nonexistent/profile.jpg")


# ---------------------------------------------------------------------------
# Generic read_file / file_exists
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Activity photos
# ---------------------------------------------------------------------------


class TestActivityPhoto:
    def test_save_returns_relative_path(self):
        aid, phid = _pid(), _pid()
        rel = storage.save_activity_photo(aid, phid, ".jpg", b"JPEG")
        assert not rel.startswith("/")

    def test_round_trip_via_read_file(self):
        aid, phid = _pid(), _pid()
        data = b"JPEG DATA"
        rel = storage.save_activity_photo(aid, phid, ".jpg", data)
        assert storage.read_file(rel) == data

    def test_extension_preserved(self):
        aid, phid = _pid(), _pid()
        rel = storage.save_activity_photo(aid, phid, ".jpg", b"data")
        assert rel.endswith(".jpg")

    def test_delete_removes_file(self):
        aid, phid = _pid(), _pid()
        rel = storage.save_activity_photo(aid, phid, ".jpg", b"data")
        storage.delete_activity_photo(rel)
        assert storage.file_exists(rel) is False

    def test_delete_nonexistent_is_silent(self):
        storage.delete_activity_photo("activities/nonexistent/photos/x.jpg")

    def test_multiple_photos_same_activity(self):
        aid = _pid()
        ph1, ph2 = _pid(), _pid()
        rel1 = storage.save_activity_photo(aid, ph1, ".jpg", b"a")
        rel2 = storage.save_activity_photo(aid, ph2, ".jpg", b"b")
        assert rel1 != rel2
        assert storage.read_file(rel1) == b"a"
        assert storage.read_file(rel2) == b"b"


# ---------------------------------------------------------------------------
# Generic read_file / file_exists
# ---------------------------------------------------------------------------


class TestGenericReadExists:
    def test_file_exists_true_after_save(self):
        lid = _pid()
        rel = storage.save_loom_photo(lid, ".jpg", b"x")
        assert storage.file_exists(rel) is True

    def test_file_exists_false_for_missing(self):
        assert storage.file_exists("not/a/real/path.txt") is False

    def test_file_exists_false_for_none(self):
        assert storage.file_exists(None) is False

    def test_file_exists_false_for_empty_string(self):
        assert storage.file_exists("") is False

    def test_read_file_returns_bytes(self):
        lid = _pid()
        rel = storage.save_loom_photo(lid, ".jpg", b"hello")
        result = storage.read_file(rel)
        assert isinstance(result, bytes)
        assert result == b"hello"

    def test_isolated_between_projects(self):
        pid1, pid2 = _pid(), _pid()
        storage.save_wif(pid1, "a.wif", b"project one")
        storage.save_wif(pid2, "a.wif", b"project two")
        rel1 = storage.save_wif(pid1, "a.wif", b"project one")
        rel2 = storage.save_wif(pid2, "a.wif", b"project two")
        assert storage.read_wif(rel1) == b"project one"
        assert storage.read_wif(rel2) == b"project two"
