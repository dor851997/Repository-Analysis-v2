"""
endpoints.py

This module sets up the FastAPI application to expose API endpoints
for repository analysis.
"""

from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
from celery.result import AsyncResult  # Import Celery result tracking
from src.repo_manager import fetch_repo_contents_task  # Import Celery task
from src.assistant import analyze_code_task  # Import Celery task
from src.logging_setup import get_tracer
from dotenv import load_dotenv
import os
import time  # Import time for logging execution time

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI()
tracer = get_tracer()

# Request model
class RepoRequest(BaseModel):
    repo_url: str

@app.post("/fetch-repo")
async def fetch_repository(request: RepoRequest):
    """
    API endpoint to fetch a GitHub repository asynchronously.
    
    Steps:
    1. Enqueue a Celery task for repo fetching
    2. Return the task ID for tracking
    """
    with tracer.start_as_current_span("fetch_repository"):
        task = fetch_repo_contents_task.delay(request.repo_url)  # Enqueue Celery task
        return {"task_id": task.id, "message": "Fetching repository in background"}

@app.post("/analyze")
async def analyze_repo(request: RepoRequest):
    """
    API endpoint to analyze a GitHub repository.
    
    Steps:
    1. Check the status of the repo fetch task
    2. If still in progress, return a message to the user
    3. If fetch is successful, proceed with AI analysis
    4. If fetch fails, retry up to 3 times before returning an error
    """
    with tracer.start_as_current_span("analyze_repo"):
        retry_attempts = 3
        backoff_time = 2  # Start with a 2-second delay

        for attempt in range(retry_attempts):
            fetch_task = AsyncResult(fetch_repo_contents_task.request.id)  # Check fetch task status

            if fetch_task.ready():
                if fetch_task.failed():
                    if attempt < retry_attempts - 1:
                        time.sleep(backoff_time)  # Exponential backoff
                        backoff_time *= 2
                        continue  # Retry fetching
                    return {"error": "Repository fetching failed after multiple attempts. Unable to proceed with analysis."}

                repo_data = fetch_task.result  # Get fetched repo data

                # Log time elapsed between fetching and analysis
                fetch_time = fetch_task.date_done.timestamp() - fetch_task.date_created.timestamp()
                tracer.get_tracer(__name__).start_as_current_span("fetch_to_analysis_time").add_event(
                    f"Time elapsed between fetching and analysis: {fetch_time:.2f} seconds"
                )

                task = analyze_code_task.delay(repo_data)  # Enqueue Celery task for AI analysis
                return {"task_id": task.id, "message": "AI analysis started"}

            time.sleep(backoff_time)  # Wait before retrying
            backoff_time *= 2  # Exponential backoff

        return {"message": "Repository fetching is still in progress. Please check task status."}

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    API endpoint to check the status of a Celery task.

    Args:
        task_id (str): The ID of the Celery task.

    Returns:
        dict: Task status and result if completed.
    """
    task_result = AsyncResult(task_id)

    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None
    }
