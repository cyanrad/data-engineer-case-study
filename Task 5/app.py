"""Task 5 - Web interface for the shopping assistant.

    python app.py                 # http://127.0.0.1:8000
    PORT=9000 python app.py       # another port

Endpoints:
    GET /                         search page
    GET /api/search?q=<text>      JSON response from ShoppingAssistant.ask (reads BigQuery)
"""

import logging
import os

from flask import Flask, jsonify, request

from assistant import ShoppingAssistant

app = Flask(__name__, static_folder="static", static_url_path="/static")
assistant = ShoppingAssistant()
log = logging.getLogger(__name__)


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/search")
def search():
    query = request.args.get("q", "")
    try:
        return jsonify(assistant.ask(query))
    except Exception:
        log.exception("search failed for query %r", query)
        return jsonify({"error": "The catalogue could not be queried in BigQuery. Check the server log."}), 502


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
