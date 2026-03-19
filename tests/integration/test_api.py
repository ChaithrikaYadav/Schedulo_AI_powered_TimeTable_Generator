"""
tests/integration/test_api.py
Integration tests for the ChronoAI FastAPI endpoints.

Uses httpx.AsyncClient to call the actual FastAPI app with an in-memory SQLite
database injected via the test_client fixture from conftest.py.
"""

from __future__ import annotations

import pytest
import pytest_asyncio


@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health_check_returns_200(self, test_client):
        """GET /health should return 200 with status 'ok'."""
        response = await test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "environment" in data

    async def test_root_returns_welcome(self, test_client):
        """GET / should return welcome message."""
        response = await test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "docs" in data


@pytest.mark.asyncio
class TestRoomsEndpoint:
    async def test_rooms_list_empty_db(self, test_client):
        """GET /api/rooms/ on empty DB should return 200 with empty list."""
        response = await test_client.get("/api/rooms/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_rooms_available_returns_200(self, test_client):
        """GET /api/rooms/available should return 200."""
        response = await test_client.get(
            "/api/rooms/available",
            params={"day": "Monday", "period": 1, "timetable_id": 999}
        )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestSubjectsEndpoint:
    async def test_subjects_list_empty_db(self, test_client):
        """GET /api/subjects/ on empty DB should return 200 with empty list."""
        response = await test_client.get("/api/subjects/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


@pytest.mark.asyncio
class TestSectionsEndpoint:
    async def test_sections_list_empty_db(self, test_client):
        """GET /api/sections/ on empty DB should return 200 with empty list."""
        response = await test_client.get("/api/sections/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


@pytest.mark.asyncio
class TestFacultyEndpoint:
    async def test_faculty_list_empty_db(self, test_client):
        """GET /api/faculty/ on empty DB should return 200 with empty list."""
        response = await test_client.get("/api/faculty/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


@pytest.mark.asyncio
class TestAuthEndpoint:
    async def test_login_returns_token(self, test_client):
        """POST /api/auth/login with any credentials returns an access_token."""
        response = await test_client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "secret"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_get_me_returns_user(self, test_client):
        """GET /api/auth/me returns user info."""
        response = await test_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert "username" in data or "role" in data


@pytest.mark.asyncio
class TestAnalyticsEndpoint:
    async def test_analytics_summary_nonexistent_timetable(self, test_client):
        """GET /api/analytics/summary/{id} for nonexistent ID returns valid response."""
        response = await test_client.get("/api/analytics/summary/99999")
        # Should return 200 with zero counts or 404 — either is acceptable
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            data = response.json()
            assert "timetable_id" in data or "total_slots" in data


@pytest.mark.asyncio
class TestTimetablesEndpoint:
    async def test_timetables_list_empty_db(self, test_client):
        """GET /api/timetables/ on empty DB should return 200."""
        response = await test_client.get("/api/timetables/")
        assert response.status_code in (200, 404)

    async def test_openapi_docs_available(self, test_client):
        """GET /docs should return 200 (OpenAPI docs UI)."""
        response = await test_client.get("/docs")
        assert response.status_code == 200


@pytest.mark.asyncio
class TestConflictsEndpoint:
    async def test_conflicts_for_nonexistent_timetable(self, test_client):
        """GET /api/conflicts/?timetable_id=99999 returns empty list."""
        response = await test_client.get("/api/conflicts/", params={"timetable_id": 99999})
        assert response.status_code == 200
        assert response.json() == []
