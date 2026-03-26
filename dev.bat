@echo off
uv run uvicorn main:app --app-dir app --port 8003 --reload
