"""
endpoints.py

This module sets up the FastAPI application to expose API endpoints
for repository analysis.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio
from celery.result import AsyncResult  # Import Celery result tracking
from src.repo_manager import fetch_repo_contents_task, celery_app  # Ensure Celery task is imported
from src.assistant import analyze_code_task  # Import Celery task
from src.logging_setup import get_tracer
from dotenv import load_dotenv
import os
import time  # Import time for logging execution time
import logging

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI()
tracer = get_tracer()
logger = logging.getLogger(__name__)

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
            # Retrieve the most recent fetch task from Celery
            fetch_task_id = fetch_repo_contents_task.delay(request.repo_url).id
            fetch_task = AsyncResult(fetch_task_id, app=celery_app)
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
    try:
        task_result = AsyncResult(task_id, app=celery_app)  # Ensure correct Celery app reference

        if task_result.backend is None:
            logger.error(f"Task {task_id} could not be retrieved: Backend is disabled.")
            raise HTTPException(status_code=500, detail="Celery result backend is not configured correctly.")

        if task_result.state == "PENDING":
            return {"task_id": task_id, "status": "PENDING", "result": None}

        if task_result.state == "FAILURE":
            logger.error(f"Task {task_id} failed: {task_result.result}")
            return {"task_id": task_id, "status": "FAILURE", "result": str(task_result.result)}

        return {
            "task_id": task_id,
            "status": task_result.state,
            "result": task_result.result if task_result.successful() else None
        }
    except AttributeError as e:
        logger.error(f"Task {task_id} retrieval failed due to missing result backend: {str(e)}")
        raise HTTPException(status_code=500, detail="Celery task result backend is not properly configured.")
    except Exception as e:
        logger.error(f"Error fetching task status for {task_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error - Failed to retrieve task status.")

