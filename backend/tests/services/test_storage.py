"""
Tests for app.services.storage.

All filesystem operations are redirected to pytest's tmp_path so no real
upload directory is touched.  The module-level `settings` object is patched
before each test via a session-scoped monkeypatch on the upload_dir attribute.
"""

import uuid
from unittest.mock import MagicMock

import pytest

import app.services.storage as storage

# Capture originals at import time — before the autouse mock_storage fixture can
# replace them.  These references let us test the real S3 code paths directly.
_real_put = storage._put
_real_get = storage._get
_real_delete = storage._delete
_real_exists = storage._exists

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

    def test_round_trip_second_save(self):
        pid = _pid()
        rel = storage.save_wif(pid, "test.wif", b"v2")
        assert storage.read_wif(rel) == b"v2"

    def test_uuid_key_format(self):
        rel = storage.save_wif(_pid(), "anything.wif", b"data")
        parts = rel.split("/")
        assert len(parts) == 2
        assert parts[0] == "drafts"
        stem = parts[1].rsplit(".", 1)[0]
        import uuid as _uuid

        _uuid.UUID(stem)  # raises if not a valid UUID

    def test_multiple_saves_produce_unique_paths(self):
        pid = _pid()
        rel1 = storage.save_wif(pid, "test.wif", b"v1")
        rel2 = storage.save_wif(pid, "test.wif", b"v2")
        assert rel1 != rel2
        assert storage.read_wif(rel1) == b"v1"
        assert storage.read_wif(rel2) == b"v2"


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
        assert storage.preview_exists("drafts/nonexistent/preview.png") is False

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
# Project photos
# ---------------------------------------------------------------------------


class TestProjectPhoto:
    def test_save_returns_relative_path(self):
        aid, phid = _pid(), _pid()
        rel = storage.save_project_photo(aid, phid, ".jpg", b"JPEG")
        assert not rel.startswith("/")

    def test_round_trip_via_read_file(self):
        aid, phid = _pid(), _pid()
        data = b"JPEG DATA"
        rel = storage.save_project_photo(aid, phid, ".jpg", data)
        assert storage.read_file(rel) == data

    def test_extension_preserved(self):
        aid, phid = _pid(), _pid()
        rel = storage.save_project_photo(aid, phid, ".jpg", b"data")
        assert rel.endswith(".jpg")

    def test_delete_removes_file(self):
        aid, phid = _pid(), _pid()
        rel = storage.save_project_photo(aid, phid, ".jpg", b"data")
        storage.delete_project_photo(rel)
        assert storage.file_exists(rel) is False

    def test_delete_nonexistent_is_silent(self):
        storage.delete_project_photo("projects/nonexistent/photos/x.jpg")

    def test_multiple_photos_same_project(self):
        aid = _pid()
        ph1, ph2 = _pid(), _pid()
        rel1 = storage.save_project_photo(aid, ph1, ".jpg", b"a")
        rel2 = storage.save_project_photo(aid, ph2, ".jpg", b"b")
        assert rel1 != rel2
        assert storage.read_file(rel1) == b"a"
        assert storage.read_file(rel2) == b"b"


# ---------------------------------------------------------------------------
# Drawdown preview
# ---------------------------------------------------------------------------


class TestDrawdownPreview:
    def test_save_returns_relative_path(self):
        rel = storage.save_drawdown_preview(b"\x89PNG")
        assert not rel.startswith("/")

    def test_uuid_key_format(self):
        rel = storage.save_drawdown_preview(b"\x89PNG")
        parts = rel.split("/")
        assert len(parts) == 2
        assert parts[0] == "drafts"
        stem = parts[1].rsplit(".", 1)[0]
        import uuid as _uuid

        _uuid.UUID(stem)

    def test_round_trip(self):
        data = b"\x89PNG\r\n\x1a\n"
        rel = storage.save_drawdown_preview(data)
        assert storage.read_drawdown_preview(rel) == data

    def test_drawdown_preview_exists_true(self):
        rel = storage.save_drawdown_preview(b"img")
        assert storage.drawdown_preview_exists(rel) is True

    def test_drawdown_preview_exists_false_for_none(self):
        assert storage.drawdown_preview_exists(None) is False

    def test_multiple_saves_unique_paths(self):
        rel1 = storage.save_drawdown_preview(b"a")
        rel2 = storage.save_drawdown_preview(b"b")
        assert rel1 != rel2


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

    def test_isolated_between_drafts(self):
        pid1, pid2 = _pid(), _pid()
        storage.save_wif(pid1, "a.wif", b"draft one")
        storage.save_wif(pid2, "a.wif", b"draft two")
        rel1 = storage.save_wif(pid1, "a.wif", b"draft one")
        rel2 = storage.save_wif(pid2, "a.wif", b"draft two")
        assert storage.read_wif(rel1) == b"draft one"
        assert storage.read_wif(rel2) == b"draft two"


# ---------------------------------------------------------------------------
# S3 code paths — use real function references captured before autouse patches
# ---------------------------------------------------------------------------


class TestS3Paths:
    @pytest.fixture(autouse=True)
    def _s3_env(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"wif bytes"))}
        monkeypatch.setattr(storage, "_s3_client", mock_client)
        monkeypatch.setattr(storage.settings, "storage_backend", "s3")
        monkeypatch.setattr(storage.settings, "s3_bucket_name", "test-bucket")
        return mock_client

    def test_put_calls_s3_put_object(self, _s3_env):
        _real_put("drafts/abc/original.wif", b"data")
        _s3_env.put_object.assert_called_once_with(Bucket="test-bucket", Key="drafts/abc/original.wif", Body=b"data")

    def test_put_returns_key(self, _s3_env):
        assert _real_put("some/key", b"x") == "some/key"

    def test_get_calls_s3_get_object(self, _s3_env):
        result = _real_get("drafts/abc/original.wif")
        _s3_env.get_object.assert_called_once_with(Bucket="test-bucket", Key="drafts/abc/original.wif")
        assert result == b"wif bytes"

    def test_delete_calls_s3_delete_object(self, _s3_env):
        _real_delete("drafts/abc/original.wif")
        _s3_env.delete_object.assert_called_once_with(Bucket="test-bucket", Key="drafts/abc/original.wif")

    def test_exists_true_when_head_succeeds(self, _s3_env):
        _s3_env.head_object.return_value = {}
        assert _real_exists("some/key") is True

    def test_exists_false_when_client_error(self, _s3_env, monkeypatch):
        from botocore.exceptions import ClientError

        _s3_env.head_object.side_effect = ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        assert _real_exists("some/key") is False

    def test_exists_false_for_empty_key(self, _s3_env):
        assert _real_exists("") is False

    def test_exists_false_for_none(self, _s3_env):
        assert _real_exists(None) is False

    def test_s3_client_constructed_when_none(self, monkeypatch):
        monkeypatch.setattr(storage, "_s3_client", None)
        monkeypatch.setattr(storage.settings, "storage_backend", "s3")
        monkeypatch.setattr(storage.settings, "s3_bucket_name", "test-bucket")
        mock_boto3_client = MagicMock()
        monkeypatch.setattr("boto3.client", mock_boto3_client)
        storage._s3()
        mock_boto3_client.assert_called_once()


# ---------------------------------------------------------------------------
# Async wrappers (asyncio.to_thread round-trips)
# ---------------------------------------------------------------------------


class TestAsyncWrappers:
    async def test_asave_wif_and_aread_file_round_trip(self):
        pid = _pid()
        key = await storage.asave_wif(pid, "test.wif", b"WIF DATA")
        assert await storage.aread_file(key) == b"WIF DATA"

    async def test_afile_exists_true_after_save(self):
        pid = _pid()
        key = await storage.asave_wif(pid, "test.wif", b"data")
        assert await storage.afile_exists(key) is True

    async def test_afile_exists_false_for_missing(self):
        assert await storage.afile_exists("no/such/file.wif") is False

    async def test_afile_exists_false_for_none(self):
        assert await storage.afile_exists(None) is False

    async def test_asave_project_photo_and_read_round_trip(self):
        pid, phid = _pid(), _pid()
        key = await storage.asave_project_photo(pid, phid, ".jpg", b"JPEG DATA")
        assert await storage.aread_file(key) == b"JPEG DATA"

    async def test_adelete_project_photo_removes_file(self):
        pid, phid = _pid(), _pid()
        key = await storage.asave_project_photo(pid, phid, ".jpg", b"data")
        await storage.adelete_project_photo(key)
        assert await storage.afile_exists(key) is False

    async def test_aread_drawdown_preview_round_trip(self):
        data = b"\x89PNG\r\n\x1a\n"
        key = storage.save_drawdown_preview(data)
        assert await storage.aread_drawdown_preview(key) == data

    async def test_asave_drawdown_preview_round_trip(self):
        data = b"\x89PNG\r\n\x1a\n"
        key = await storage.asave_drawdown_preview(data)
        assert storage.read_drawdown_preview(key) == data


# ---------------------------------------------------------------------------
# Local backend primitives — cover lines 50-52, 59, 67-69, 83
# ---------------------------------------------------------------------------


class TestLocalBackendPrimitives:
    @pytest.fixture(autouse=True)
    def _local_mode(self, monkeypatch):
        monkeypatch.setattr(storage.settings, "storage_backend", "local")

    def test_put_writes_bytes_to_disk(self, tmp_path):
        result = _real_put("test/file.wif", b"hello local")
        assert result == "test/file.wif"
        assert (tmp_path / "test" / "file.wif").read_bytes() == b"hello local"

    def test_put_creates_missing_parent_dirs(self, tmp_path):
        _real_put("a/b/c/deep.wif", b"deep")
        assert (tmp_path / "a" / "b" / "c" / "deep.wif").exists()

    def test_get_reads_bytes_from_disk(self, tmp_path):
        (tmp_path / "read_me.txt").write_bytes(b"file content")
        assert _real_get("read_me.txt") == b"file content"

    def test_delete_removes_existing_file(self, tmp_path):
        (tmp_path / "remove_me.wif").write_bytes(b"x")
        _real_delete("remove_me.wif")
        assert not (tmp_path / "remove_me.wif").exists()

    def test_delete_missing_file_is_silent(self):
        _real_delete("not/there/file.wif")

    def test_exists_returns_true_for_existing_file(self, tmp_path):
        (tmp_path / "present.wif").write_bytes(b"y")
        assert _real_exists("present.wif") is True

    def test_exists_returns_false_for_missing_file(self):
        assert _real_exists("absent/file.wif") is False


# ---------------------------------------------------------------------------
# Drawdown tile functions — cover lines 138, 142, 146, 150, 154
# ---------------------------------------------------------------------------


class TestDrawdownTileFunctions:
    @pytest.fixture(autouse=True)
    def _local_mode(self, monkeypatch):
        monkeypatch.setattr(storage.settings, "storage_backend", "local")

    def test_drawdown_tile_path_format(self):
        did = _pid()
        path = storage.drawdown_tile_path(did, 2, 100)
        assert path == f"drafts/{did}/tiles/s2/t100.png"

    def test_save_and_tile_exists_true(self):
        did = _pid()
        storage.save_drawdown_tile(did, 1, 0, b"PNG")
        assert storage.drawdown_tile_exists(did, 1, 0) is True

    def test_tile_not_exists_before_save(self):
        assert storage.drawdown_tile_exists(_pid(), 1, 0) is False

    def test_save_and_read_round_trip(self):
        did = _pid()
        storage.save_drawdown_tile(did, 2, 50, b"TILE DATA")
        assert storage.read_drawdown_tile(did, 2, 50) == b"TILE DATA"

    async def test_adrawdown_tile_exists_true(self):
        did = _pid()
        storage.save_drawdown_tile(did, 1, 0, b"PNG")
        assert await storage.adrawdown_tile_exists(did, 1, 0) is True

    async def test_adrawdown_tile_exists_false(self):
        assert await storage.adrawdown_tile_exists(_pid(), 1, 0) is False

    async def test_aread_drawdown_tile_round_trip(self):
        did = _pid()
        storage.save_drawdown_tile(did, 1, 0, b"ASYNC READ")
        assert await storage.aread_drawdown_tile(did, 1, 0) == b"ASYNC READ"

    async def test_asave_drawdown_tile_round_trip(self):
        did = _pid()
        await storage.asave_drawdown_tile(did, 1, 0, b"ASYNC SAVE")
        assert storage.read_drawdown_tile(did, 1, 0) == b"ASYNC SAVE"


# ---------------------------------------------------------------------------
# Project tile functions — cover lines 170-187
# ---------------------------------------------------------------------------


class TestProjectTileFunctions:
    @pytest.fixture(autouse=True)
    def _local_mode(self, monkeypatch):
        monkeypatch.setattr(storage.settings, "storage_backend", "local")

    def test_project_tile_path_format(self):
        pid = _pid()
        path = storage.project_tile_path(pid, 2, 100)
        assert path == f"projects/{pid}/tiles/s2/r100.png"

    def test_save_and_tile_exists_true(self):
        pid = _pid()
        storage.save_project_tile(pid, 1, 0, b"PNG")
        assert storage.project_tile_exists(pid, 1, 0) is True

    def test_tile_not_exists_before_save(self):
        assert storage.project_tile_exists(_pid(), 1, 0) is False

    def test_save_and_read_round_trip(self):
        pid = _pid()
        storage.save_project_tile(pid, 2, 50, b"TILE DATA")
        assert storage.read_project_tile(pid, 2, 50) == b"TILE DATA"

    async def test_aproject_tile_exists_true(self):
        pid = _pid()
        storage.save_project_tile(pid, 1, 0, b"PNG")
        assert await storage.aproject_tile_exists(pid, 1, 0) is True

    async def test_aproject_tile_exists_false(self):
        assert await storage.aproject_tile_exists(_pid(), 1, 0) is False

    async def test_aread_project_tile_round_trip(self):
        pid = _pid()
        storage.save_project_tile(pid, 1, 0, b"ASYNC READ")
        assert await storage.aread_project_tile(pid, 1, 0) == b"ASYNC READ"

    async def test_asave_project_tile_round_trip(self):
        pid = _pid()
        await storage.asave_project_tile(pid, 1, 0, b"ASYNC SAVE")
        assert storage.read_project_tile(pid, 1, 0) == b"ASYNC SAVE"


# ---------------------------------------------------------------------------
# Project drawdown preview and SVG — cover lines 190-211
# ---------------------------------------------------------------------------


class TestProjectDrawdownAndSvg:
    @pytest.fixture(autouse=True)
    def _local_mode(self, monkeypatch):
        monkeypatch.setattr(storage.settings, "storage_backend", "local")

    def test_save_project_drawdown_preview_returns_path(self):
        rel = storage.save_project_drawdown_preview(b"\x89PNG")
        assert rel.startswith("projects/") and rel.endswith(".png")

    def test_project_drawdown_preview_round_trip(self):
        data = b"\x89PNG\r\n\x1a\n"
        rel = storage.save_project_drawdown_preview(data)
        assert storage.read_project_drawdown_preview(rel) == data

    def test_project_drawdown_preview_exists_true(self):
        rel = storage.save_project_drawdown_preview(b"img")
        assert storage.project_drawdown_preview_exists(rel) is True

    def test_project_drawdown_preview_exists_false_for_none(self):
        assert storage.project_drawdown_preview_exists(None) is False

    def test_project_drawdown_preview_exists_false_for_missing(self):
        assert storage.project_drawdown_preview_exists("projects/no.png") is False

    def test_save_project_drawdown_svg_returns_path(self):
        rel = storage.save_project_drawdown_svg("<svg/>")
        assert rel.startswith("projects/") and rel.endswith(".svg")

    def test_project_drawdown_svg_round_trip(self):
        data = "<svg><rect/></svg>"
        rel = storage.save_project_drawdown_svg(data)
        assert storage.read_project_drawdown_svg(rel) == data

    def test_project_drawdown_svg_exists_true(self):
        rel = storage.save_project_drawdown_svg("<svg/>")
        assert storage.project_drawdown_svg_exists(rel) is True

    def test_project_drawdown_svg_exists_false_for_none(self):
        assert storage.project_drawdown_svg_exists(None) is False


# ---------------------------------------------------------------------------
# delete_project_tiles — cover lines 216-236
#
# Note: conftest mock_storage replaces _put/_get/_delete/_exists with an
# in-memory dict, so delete_project_tiles (which checks the real filesystem
# in local mode) must be seeded with _real_put (captured before the mock runs).
# ---------------------------------------------------------------------------


class TestDeleteProjectTiles:
    @pytest.fixture(autouse=True)
    def _local_mode(self, monkeypatch):
        monkeypatch.setattr(storage.settings, "storage_backend", "local")

    def test_local_returns_zero_when_no_tiles(self):
        assert storage.delete_project_tiles(_pid()) == 0

    def test_local_deletes_tiles_and_returns_count(self):
        pid = _pid()
        _real_put(storage.project_tile_path(pid, 1, 0), b"a")
        _real_put(storage.project_tile_path(pid, 1, 50), b"b")
        _real_put(storage.project_tile_path(pid, 2, 0), b"c")
        count = storage.delete_project_tiles(pid)
        assert count == 3

    def test_local_only_deletes_target_project_tiles(self, tmp_path):
        pid1, pid2 = _pid(), _pid()
        _real_put(storage.project_tile_path(pid1, 1, 0), b"p1")
        _real_put(storage.project_tile_path(pid2, 1, 0), b"p2")
        storage.delete_project_tiles(pid1)
        assert (tmp_path / storage.project_tile_path(pid2, 1, 0)).exists()

    def test_s3_path_uses_paginator_and_delete_objects(self, monkeypatch):
        mock_client = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Contents": [{"Key": "projects/x/tiles/s1/r0.png"}]}]
        mock_client.get_paginator.return_value = paginator
        monkeypatch.setattr(storage, "_s3_client", mock_client)
        monkeypatch.setattr(storage.settings, "storage_backend", "s3")
        monkeypatch.setattr(storage.settings, "s3_bucket_name", "test-bucket")

        count = storage.delete_project_tiles(_pid())
        assert count == 1
        mock_client.delete_objects.assert_called_once()

    def test_s3_empty_page_skips_delete_objects(self, monkeypatch):
        mock_client = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{}]
        mock_client.get_paginator.return_value = paginator
        monkeypatch.setattr(storage, "_s3_client", mock_client)
        monkeypatch.setattr(storage.settings, "storage_backend", "s3")
        monkeypatch.setattr(storage.settings, "s3_bucket_name", "test-bucket")

        count = storage.delete_project_tiles(_pid())
        assert count == 0
        mock_client.delete_objects.assert_not_called()


# ---------------------------------------------------------------------------
# copy_file — cover lines 321-322
# ---------------------------------------------------------------------------


class TestCopyFile:
    @pytest.fixture(autouse=True)
    def _local_mode(self, monkeypatch):
        monkeypatch.setattr(storage.settings, "storage_backend", "local")

    def test_copy_creates_new_key_with_same_content(self):
        pid = _pid()
        old_key = storage.save_wif(pid, "original.wif", b"COPY ME")
        new_key = f"drafts/{uuid.uuid4()}.wif"
        result = storage.copy_file(old_key, new_key)
        assert result == new_key
        assert storage.read_wif(new_key) == b"COPY ME"

    def test_copy_does_not_remove_original(self):
        pid = _pid()
        old_key = storage.save_wif(pid, "original.wif", b"ORIGINAL")
        storage.copy_file(old_key, f"drafts/{uuid.uuid4()}.wif")
        assert storage.read_wif(old_key) == b"ORIGINAL"


# ---------------------------------------------------------------------------
# Additional async wrappers — cover lines 345, 365, 369, 375, 379, 385, 389,
# 393, 397, 401, 405, 409, 413, 417, 421
# ---------------------------------------------------------------------------


class TestAsyncWrappersExtended:
    @pytest.fixture(autouse=True)
    def _local_mode(self, monkeypatch):
        monkeypatch.setattr(storage.settings, "storage_backend", "local")

    async def test_asave_preview_creates_file(self):
        key = await storage.asave_preview(_pid(), b"\x89PNG")
        assert storage.preview_exists(key) is True

    async def test_asave_loom_photo_round_trip(self):
        key = await storage.asave_loom_photo(_pid(), ".jpg", b"JPEG")
        assert storage.file_exists(key) is True

    async def test_adelete_loom_photo_removes_file(self):
        key = await storage.asave_loom_photo(_pid(), ".jpg", b"JPEG")
        await storage.adelete_loom_photo(key)
        assert storage.file_exists(key) is False

    async def test_asave_version_photo_round_trip(self):
        key = await storage.asave_version_photo(_pid(), _pid(), _pid(), ".jpg", b"PHOTO")
        assert storage.file_exists(key) is True

    async def test_adelete_version_photo_removes_file(self):
        key = await storage.asave_version_photo(_pid(), _pid(), _pid(), ".jpg", b"PHOTO")
        await storage.adelete_version_photo(key)
        assert storage.file_exists(key) is False

    async def test_asave_version_receipt_round_trip(self):
        key = await storage.asave_version_receipt(_pid(), _pid(), _pid(), ".pdf", b"PDF")
        assert storage.file_exists(key) is True

    async def test_adelete_version_receipt_removes_file(self):
        key = await storage.asave_version_receipt(_pid(), _pid(), _pid(), ".pdf", b"PDF")
        await storage.adelete_version_receipt(key)
        assert storage.file_exists(key) is False

    async def test_asave_yarn_photo_round_trip(self):
        key = await storage.asave_yarn_photo(_pid(), ".jpg", b"YARN")
        assert storage.file_exists(key) is True

    async def test_adelete_yarn_photo_removes_file(self):
        key = await storage.asave_yarn_photo(_pid(), ".jpg", b"YARN")
        await storage.adelete_yarn_photo(key)
        assert storage.file_exists(key) is False

    async def test_asave_project_drawdown_preview_round_trip(self):
        key = await storage.asave_project_drawdown_preview(b"\x89PNG")
        assert await storage.aread_project_drawdown_preview(key) == b"\x89PNG"

    async def test_aproject_drawdown_preview_exists_true(self):
        key = await storage.asave_project_drawdown_preview(b"img")
        assert await storage.aproject_drawdown_preview_exists(key) is True

    async def test_aproject_drawdown_preview_exists_false_for_none(self):
        assert await storage.aproject_drawdown_preview_exists(None) is False

    async def test_asave_project_drawdown_svg_round_trip(self):
        key = await storage.asave_project_drawdown_svg("<svg/>")
        assert await storage.aread_project_drawdown_svg(key) == "<svg/>"

    async def test_aproject_drawdown_svg_exists_true(self):
        key = await storage.asave_project_drawdown_svg("<svg/>")
        assert await storage.aproject_drawdown_svg_exists(key) is True

    async def test_aproject_drawdown_svg_exists_false_for_none(self):
        assert await storage.aproject_drawdown_svg_exists(None) is False
