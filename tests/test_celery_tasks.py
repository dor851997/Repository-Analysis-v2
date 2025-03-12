import pytest
from unittest.mock import patch
from src.repo_manager import fetch_repo_contents_task

def test_fetch_repo_contents_task():
    repo_url = "https://github.com/django/django"
    
    with patch("src.repo_manager.fetch_repo_contents", return_value={"repo_url": repo_url, "files": {"README.md": "content"}}):
        result = fetch_repo_contents_task(repo_url)

        assert "repo_url" in result
        assert "files" in result
        assert "README.md" in result["files"]