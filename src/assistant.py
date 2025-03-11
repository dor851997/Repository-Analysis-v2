"""
assistant.py

This module interacts with OpenAI's Assistant API to analyze repository code using Celery for background processing.
"""

import asyncio
import os
import openai
import json
import redis
import time
import logging
from dotenv import load_dotenv
from celery import Celery
from opentelemetry import trace, metrics

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CACHE_EXPIRY = 86400  # 24 hours (in seconds)

# Initialize Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Initialize Celery
celery_app = Celery("tasks", broker="redis://localhost:6379/0")

# Initialize OpenTelemetry Tracer & Metrics
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Define OpenTelemetry Metrics
ai_request_counter = meter.create_counter(
    name="ai_request_count",
    description="Counts the number of AI requests",
)

ai_request_duration = meter.create_histogram(
    name="ai_request_duration",
    description="Measures AI request response time",
)

ai_request_failures = meter.create_counter(
    name="ai_request_failures",
    description="Counts AI request failures",
)

# OpenAI Vector Database API Configuration
VECTOR_STORE_NAME = "repo_code_vectors"

async def store_code_embeddings(repo_data: dict):
    """
    Converts repository code snippets into vector embeddings and stores them in OpenAI's vector database.

    Args:
        repo_data (dict): Dictionary containing repository file paths and contents.
    """
    try:
        for file_path, code in repo_data.get("files", {}).items():
            # Generate embedding for the code snippet
            response = await openai.Embedding.acreate(
                input=code,
                model="text-embedding-ada-002"
            )
            embedding = response["data"][0]["embedding"]

            # Check if the embedding already exists
            existing_vectors = await openai.VectorStore.asearch(
                name=VECTOR_STORE_NAME,
                query=embedding,
                top_k=1  # Check for an exact match
            )

            if existing_vectors["matches"] and existing_vectors["matches"][0]["metadata"]["file_path"] == file_path:
                logger.info(f"Embedding for {file_path} already exists, skipping storage.")
                continue  # Skip storing duplicate embeddings

            # Store or update the embedding in OpenAI's Vector Database
            logger.info(f"Storing embedding for {file_path} in vector database.")
            await openai.VectorStore.acreate(
                name=VECTOR_STORE_NAME,
                vectors=[{"id": file_path, "values": embedding, "metadata": {"repo_url": repo_data["repo_url"], "file_path": file_path}}]
            )
    
    except Exception as e:
        logger.error(f"Error storing embeddings: {str(e)}")

async def search_similar_code(query: str):
    """
    Searches for code snippets similar to the given query in OpenAI's Vector Database.

    Args:
        query (str): User query describing the desired code.

    Returns:
        list: List of matching code snippets.
    """
    try:
        start_time = time.time()  # Track search execution time

        response = await openai.Embedding.acreate(
            input=query,
            model="text-embedding-ada-002"
        )
        query_embedding = response["data"][0]["embedding"]

        # Perform vector search in OpenAI's database
        search_results = await openai.VectorStore.asearch(
            name=VECTOR_STORE_NAME,
            query=query_embedding,
            top_k=5  # Retrieve top 5 most relevant matches
        )

        elapsed_time = time.time() - start_time
        logger.info(f"Vector search executed in {elapsed_time:.3f} seconds, retrieved {len(search_results['matches'])} results.")

        results = []
        for match in search_results["matches"]:
            results.append({
                "file_path": match["metadata"]["file_path"],
                "repo_url": match["metadata"]["repo_url"],
                "similarity_score": match["score"]
            })

        return results

    except Exception as e:
        logger.error(f"Error searching code embeddings: {str(e)}")
        return []

@celery_app.task(bind=True)
def analyze_code_task(self, repo_data: dict) -> str:
    """
    Celery task to process AI-based repository analysis in the background.

    Args:
        repo_data (dict): The repository contents (files and their code).

    Returns:
        str: AI-generated analysis of the repository.
    """
    task_id = self.request.id  # Get Celery Task ID
    logger.info(f"Starting Celery Task: {task_id}")

    if not OPENAI_API_KEY:
        logger.error(f"Task {task_id} failed: OpenAI API key is missing.")
        return "Error: OpenAI API key is missing."

    cache_key = f"ai_analysis:{hash(json.dumps(repo_data, sort_keys=True))}"
    cached_result = redis_client.get(cache_key)

    if cached_result:
        logger.info(f"Task {task_id}: Returning cached AI response.")
        return cached_result  # Return cached AI response

    with tracer.start_as_current_span("analyze_code"):
        ai_request_counter.add(1)  # Increment request counter
        start_time = time.time()

        try:
            prompt = (
                "You are an advanced AI that specializes in analyzing GitHub repositories. "
                "Analyze the provided repository contents and provide structured insights, including:\n"
                "- **Code Complexity**: Identify overly complex functions or areas needing refactoring.\n"
                "- **Security Issues**: Highlight potential vulnerabilities.\n"
                "- **Best Practices**: Suggest improvements based on coding standards.\n"
                "- **Documentation Gaps**: Identify missing or inadequate documentation.\n"
                "Repository contents:\n"
                f"{json.dumps(repo_data, indent=2)}"
            )

            response = openai.ChatCompletion.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are an AI assistant specialized in analyzing code repositories."},
                    {"role": "user", "content": prompt}
                ],
                api_key=OPENAI_API_KEY
            )

            analysis_result = response["choices"][0]["message"]["content"]

            # Log response quality
            span = trace.get_current_span()
            span.add_event("AI Response Generated", {
                "task_id": task_id,
                "response_length": len(analysis_result),
                "is_truncated": "..." in analysis_result
            })

            # Cache the result for future queries
            redis_client.setex(cache_key, CACHE_EXPIRY, analysis_result)

            ai_request_duration.record(time.time() - start_time)  # Log response time
            logger.info(f"Task {task_id} completed successfully.")

            return analysis_result

        except openai.error.OpenAIError as e:
            ai_request_failures.add(1)  # Increment failure count
            ai_request_duration.record(time.time() - start_time)  # Log failed request time
            span = trace.get_current_span()
            span.add_event("AI Request Failed", {
                "task_id": task_id,
                "error": str(e)
            })
            logger.error(f"Task {task_id} failed: {str(e)}")
            return f"Error: {str(e)}"

