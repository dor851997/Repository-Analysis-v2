import pytest
from httpx import AsyncClient
from src.endpoints import app

@pytest.mark.asyncio
async def test_fetch_repo_api():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/fetch-repo", json={"repo_url": "https://github.com/django/django"})
    
    assert response.status_code == 200
    assert "task_id" in response.json()