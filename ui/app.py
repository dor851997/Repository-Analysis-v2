"""
app.py

This module sets up the Streamlit UI for users to input a GitHub repo URL
and receive AI-generated insights.
"""

import streamlit as st
import requests

# FastAPI backend URL
API_URL = "http://localhost:8000/analyze"

st.title("Repository Analysis v2")

# Input field for repository URL
repo_url = st.text_input("Enter GitHub Repository URL", "")

if st.button("Analyze Repo"):
    if repo_url:
        with st.spinner("Analyzing..."):
            response = requests.post(API_URL, json={"repo_url": repo_url})
            if response.status_code == 200:
                analysis = response.json()
                st.subheader("Analysis Results")
                st.json(analysis)  # Display results as JSON
            else:
                st.error("Error analyzing the repository.")
    else:
        st.warning("Please enter a valid GitHub repository URL.")