from flask import Flask, render_template, request, Response, jsonify, stream_with_context
import os
import re
import json
import time
import queue
import threading
from dotenv import load_dotenv

load_dotenv()

from agents import get_gemini_llm, DEFAULT_MODEL
from pipeline import run_research_pipeline

app = Flask(__name__)
app.secret_key = os.urandom(24)

AVAILABLE_MODELS = [
    {
        "id": "gemini-3.5-flash-lite",
        "name": "Gemini 3.5 Flash Lite (Recommended - High Speed, 15-30 RPM Free Plan)",
        "badge": "Free Tier Optimized"
    },
    {
        "id": "gemini-3.5-flash",
        "name": "Gemini 3.5 Flash (Deep Multimodal Reasoning)",
        "badge": "High Depth"
    },
    {
        "id": "gemini-3.8-flash",
        "name": "Gemini 3.8 Flash (Latest Preview Architecture)",
        "badge": "Advanced"
    },
]


def parse_score(feedback: str) -> str:
    """Extract score from critic feedback text."""
    match = re.search(r"Score:\s*(\d+(\.\d+)?\s*/\s*10)", feedback, re.IGNORECASE)
    if match:
        return match.group(1).replace(" ", "")
    match_num = re.search(r"(\d+(\.\d+)?)\s*/\s*10", feedback)
    if match_num:
        return f"{match_num.group(1)}/10"
    return "Evaluated"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    google_key = os.getenv("GOOGLE_API_KEY", "")
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    return jsonify({
        "has_google_key": bool(google_key.strip()),
        "has_tavily_key": bool(tavily_key.strip()),
        "google_masked": f"{google_key[:6]}...{google_key[-4:]}" if len(google_key) > 10 else ("Set" if google_key else ""),
        "tavily_masked": f"{tavily_key[:4]}...{tavily_key[-4:]}" if len(tavily_key) > 8 else ("Set" if tavily_key else ""),
        "models": AVAILABLE_MODELS,
        "default_model": DEFAULT_MODEL,
        "rate_limits": {
            "rpm": "15-30 Requests/min",
            "tpm": "1,000,000 Tokens/min",
            "rpd": "1,500 Requests/day",
            "note": "Optimized with 1s stage pacing & 3,000 char scrape cap to protect your free tier quota."
        }
    })


@app.route("/api/config", methods=["POST"])
def update_config():
    data = request.get_json() or {}
    google_key = data.get("google_key", "").strip()
    tavily_key = data.get("tavily_key", "").strip()

    if google_key:
        os.environ["GOOGLE_API_KEY"] = google_key
    if tavily_key:
        os.environ["TAVILY_API_KEY"] = tavily_key

    return jsonify({"status": "success", "message": "API keys updated successfully"})


@app.route("/api/research/stream")
def stream_research():
    topic = request.args.get("topic", "").strip()
    model_name = request.args.get("model", DEFAULT_MODEL).strip()
    try:
        temperature = float(request.args.get("temperature", 0.0))
    except (ValueError, TypeError):
        temperature = 0.0

    google_key = request.args.get("google_key", "").strip() or os.getenv("GOOGLE_API_KEY", "")
    tavily_key = request.args.get("tavily_key", "").strip() or os.getenv("TAVILY_API_KEY", "")

    if not topic:
        return jsonify({"error": "Topic parameter is required"}), 400

    if not google_key:
        return jsonify({"error": "Google Gemini API Key missing. Please set GOOGLE_API_KEY in .env or Settings."}), 400

    if not tavily_key:
        return jsonify({"error": "Tavily API Key missing. Please set TAVILY_API_KEY in .env or Settings."}), 400

    # Ensure environment variables are active
    os.environ["GOOGLE_API_KEY"] = google_key
    os.environ["TAVILY_API_KEY"] = tavily_key

    event_queue = queue.Queue()

    def progress_callback(step_num, message, status_state, data=None):
        payload = {
            "type": "progress",
            "step": step_num,
            "message": message,
            "status": status_state,
            "data": data,
            "timestamp": time.time()
        }
        event_queue.put(payload)

    def worker():
        try:
            custom_llm = get_gemini_llm(
                model_name=model_name,
                temperature=temperature,
                api_key=google_key
            )
            result = run_research_pipeline(
                topic=topic,
                custom_llm=custom_llm,
                progress_callback=progress_callback
            )
            # Add calculated score
            result["score"] = parse_score(result.get("feedback", ""))
            result["model"] = model_name
            event_queue.put({"type": "complete", "result": result})
        except Exception as e:
            event_queue.put({"type": "error", "error": str(e)})
        finally:
            event_queue.put(None)  # Sentinel to end stream

    threading.Thread(target=worker, daemon=True).start()

    def sse_generator():
        while True:
            try:
                item = event_queue.get(timeout=120)
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                # Keep-alive heartbeat
                yield f": ping\n\n"

    response = Response(
        stream_with_context(sse_generator()),
        mimetype="text/event-stream"
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response


@app.route("/api/research", methods=["POST"])
def run_research_json():
    data = request.get_json() or {}
    topic = data.get("topic", "").strip()
    model_name = data.get("model", DEFAULT_MODEL).strip()
    try:
        temperature = float(data.get("temperature", 0.0))
    except (ValueError, TypeError):
        temperature = 0.0

    google_key = data.get("google_key", "").strip() or os.getenv("GOOGLE_API_KEY", "")
    tavily_key = data.get("tavily_key", "").strip() or os.getenv("TAVILY_API_KEY", "")

    if not topic:
        return jsonify({"error": "Topic is required"}), 400

    if not google_key or not tavily_key:
        return jsonify({"error": "API keys missing"}), 400

    os.environ["GOOGLE_API_KEY"] = google_key
    os.environ["TAVILY_API_KEY"] = tavily_key

    try:
        custom_llm = get_gemini_llm(model_name=model_name, temperature=temperature, api_key=google_key)
        result = run_research_pipeline(topic=topic, custom_llm=custom_llm)
        result["score"] = parse_score(result.get("feedback", ""))
        result["model"] = model_name
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
