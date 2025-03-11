"""
repo_manager.py

This module handles fetching GitHub repositories for analysis using the GitHub API.
"""

import os
import asyncio
import aiohttp
import redis
import json
import time
from dotenv import load_dotenv
from opentelemetry import trace
from celery import Celery

# Load environment variables
load_dotenv()

GITHUB_API_TOKEN = os.getenv("GITHUB_API_TOKEN")
CACHE_EXPIRY = 86400  # 24 hours (in seconds)

# Initialize Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Initialize Celery
celery_app = Celery("tasks", broker="redis://localhost:6379/0")

# OpenTelemetry Tracer
tracer = trace.get_tracer(__name__)

@celery_app.task(bind=True)
def fetch_repo_contents_task(self, repo_url: str) -> dict:
    """
    Celery task to fetch repository contents asynchronously.

    Args:
        repo_url (str): The GitHub repository URL.

    Returns:
        dict: Dictionary containing repo file paths and their contents.
    """
    return asyncio.run(fetch_repo_contents(repo_url))

async def fetch_repo_contents(repo_url: str) -> dict:
    """
    Fetch repository contents from GitHub asynchronously, with caching.

    Args:
        repo_url (str): The GitHub repository URL.

    Returns:
        dict: Dictionary containing repo file paths and their contents.
    """
    with tracer.start_as_current_span("fetch_repo_contents"):
        cache_key = f"repo_cache:{repo_url}"
        cached_data = redis_client.get(cache_key)

        if cached_data:
            tracer.add_event("Cache hit")
            return json.loads(cached_data)  # Return cached repo data

        tracer.add_event("Cache miss, fetching from GitHub")

        repo_owner, repo_name = extract_repo_details(repo_url)
        if not repo_owner or not repo_name:
            return {"error": "Invalid GitHub repository URL format."}

        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents"
        headers = {"Authorization": f"token {GITHUB_API_TOKEN}"} if GITHUB_API_TOKEN else {}

        async with aiohttp.ClientSession() as session:
            try:
                start_time = time.time()
                async with session.get(api_url, headers=headers) as response:
                    duration = time.time() - start_time
                    tracer.add_event(f"GitHub API request took {duration:.2f} seconds")

                    if response.status == 200:
                        file_data = await response.json()
                        repo_files = await process_repo_files(file_data, session)

                        # Store in Redis cache with timestamp
                        repo_cache = {
                            "repo_url": repo_url,
                            "files": repo_files,
                            "timestamp": time.time(),
                        }
                        redis_client.setex(cache_key, CACHE_EXPIRY, json.dumps(repo_cache))

                        return repo_cache
                    elif response.status == 403:
                        tracer.add_event("GitHub API rate limit exceeded")
                        return {"error": "GitHub API rate limit exceeded. Try again later."}
                    elif response.status == 404:
                        return {"error": "Repository not found. Check if the URL is correct."}
                    else:
                        return {"error": f"Unexpected error from GitHub API: {response.status}"}
            except Exception as e:
                tracer.add_event(f"Exception occurred: {str(e)}")
                return {"error": "An error occurred while fetching the repository."}

async def process_repo_files(file_data, session):
    """
    Process repository file structure and fetch file contents.

    Args:
        file_data (list): List of files from the GitHub API.
        session (aiohttp.ClientSession): Async session for HTTP requests.

    Returns:
        dict: Dictionary of file paths and their contents.
    """
    repo_files = {}
    tasks = []

    for file in file_data:
        if file["type"] == "file":  # Skip directories
            tasks.append(fetch_file_content(file["download_url"], session))

    file_contents = await asyncio.gather(*tasks)

    for file, content in zip(file_data, file_contents):
        repo_files[file["path"]] = content

    return repo_files

async def fetch_file_content(file_url: str, session) -> str:
    """
    Fetches the content of an individual file.

    Args:
        file_url (str): URL to the file's raw content.
        session (aiohttp.ClientSession): Async session for HTTP requests.

    Returns:
        str: File content as text.
    """
    async with session.get(file_url) as response:
        if response.status == 200:
            return await response.text()
        return f"Error fetching file: {response.status}"

def extract_repo_details(repo_url: str) -> tuple:
    """
    Extract repository owner and name from a GitHub URL.

    Args:
        repo_url (str): The GitHub repository URL.

    Returns:
        tuple: (owner, repo_name)
    """
    parts = repo_url.strip("/").split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, None

def invalidate_cache(repo_url: str):
    """
    Clears the cached repository data.

    Args:
        repo_url (str): The GitHub repository URL.
    """
    cache_key = f"repo_cache:{repo_url}"
    redis_client.delete(cache_key)
