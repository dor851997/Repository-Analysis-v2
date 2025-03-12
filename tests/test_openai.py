import pytest
from unittest.mock import AsyncMock, patch
from src.assistant import store_code_embeddings

@pytest.mark.asyncio
async def test_store_code_embeddings():
    mock_openai_response = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    with patch("openai.Embedding.acreate", AsyncMock(return_value=mock_openai_response)):
        repo_data = {"repo_url": "https://github.com/example/repo", "files": {"test.py": "print('Hello')"}}
        await store_code_embeddings(repo_data)

        assert True  # If no error occurs, test passes