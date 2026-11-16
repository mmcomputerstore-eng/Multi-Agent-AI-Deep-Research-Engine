"""
Main Launcher for the Multi-Agent Research System (Flask Web Application).

Run this file to start the Flask web application:
    python main.py
Or:
    python app.py
"""

import os
from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("🚀 Starting Flask Multi-Agent AI Research Server...")
    print(f"🌐 Local URL: http://localhost:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=True)
