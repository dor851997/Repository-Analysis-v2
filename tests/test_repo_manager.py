import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch
from src.repo_manager import fetch_repo_contents

@pytest.mark.asyncio
async def test_fetch_repo_contents_success():
    repo_url = "https://github.com/django/django"
    mock_response = [{"path": "README.md", "type": "file", "download_url": "https://raw.githubusercontent.com/django/django/main/README.md"}]

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)

        result = await fetch_repo_contents(repo_url)

        assert "files" in result
        assert "README.md" in result["files"]