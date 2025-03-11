"""
endpoints.py

This module sets up the FastAPI application to expose API endpoints
for repository analysis.
"""

from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
from src.repo_manager import fetch_repo
from src.assistant import analyze_code
from src.logging_setup import get_tracer
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI()
tracer = get_tracer()

# Request model
class RepoRequest(BaseModel):
    repo_url: str

@app.post("/analyze")
async def analyze_repo(request: RepoRequest):
    """
    API endpoint to analyze a GitHub repository.
    
    Steps:
    1. Fetch repository data
    2. Send code to OpenAI for analysis
    3. Return insights to the user
    """
    with tracer.start_as_current_span("analyze_repo"):
        repo_data = await fetch_repo(request.repo_url)  # Fetch repo data
        insights = await analyze_code(repo_data)  # Analyze with AI
        return {"repo_url": request.repo_url, "insights": insights}