#!/bin/bash

# Start Redis if it's not already running
if ! pgrep -x "redis-server" > /dev/null
then
    echo "Starting Redis..."
    redis-server --daemonize yes
else
    echo "Redis is already running."
fi

# Activate virtual environment (if using one)
# source venv/bin/activate  # For Mac/Linux
# venv\Scripts\activate  # For Windows

echo "Starting Celery workers..."
celery -A src.repo_manager.celery_app worker --loglevel=info &  # Repo fetching worker
celery -A src.assistant.celery_app worker --loglevel=info &  # AI analysis worker

echo "Starting FastAPI backend..."
uvicorn src.endpoints:app --reload &  # Run FastAPI in background

sleep 2  # Wait for FastAPI to start

echo "Starting Streamlit UI..."
streamlit run ui/app.py  # Run Streamlit

wait  # Keep script running until processes exit