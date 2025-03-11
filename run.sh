#!/bin/bash

# Activate virtual environment (uncomment if using a venv)
# source venv/bin/activate  # For Mac/Linux
# venv\Scripts\activate  # For Windows (uncomment if needed)

echo "Starting FastAPI backend..."
uvicorn src.endpoints:app --reload &  # Run FastAPI in background

sleep 2  # Wait for FastAPI to start

echo "Starting Streamlit UI..."
streamlit run ui/app.py  # Run Streamlit

wait  # Keep script running until processes exit