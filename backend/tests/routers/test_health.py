from httpx import AsyncClient

from app.version import VERSION


class TestHealth:
    async def test_returns_200(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_status_is_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.json()["status"] == "ok"

    async def test_returns_version(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.json()["version"] == VERSION

    async def test_response_schema(self, client: AsyncClient):
        resp = await client.get("/health")
        body = resp.json()
        assert "status" in body
        assert "version" in body
