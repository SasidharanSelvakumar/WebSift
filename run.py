#!/usr/bin/env python3
"""
WebSift - Application Launcher
Runs the FastAPI backend and serves the compiled React + TypeScript frontend.
"""
import os
import sys
import webbrowser
from pathlib import Path
import uvicorn

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

def main():
    print("=" * 70)
    print("  WebSift — Web Scraping & Content Export Agent")
    print("=" * 70)
    print(f"  • Root Directory : {ROOT_DIR}")
    print(f"  • Frontend Built : {'Yes' if FRONTEND_DIST.exists() else 'No (API only)'}")
    print("  • Server URL     : http://127.0.0.1:8000")
    print("=" * 70)
    print("Starting WebSift server (Press Ctrl+C to stop)...")
    
    # Run uvicorn
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )

if __name__ == "__main__":
    main()
