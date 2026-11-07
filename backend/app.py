from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000"])


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Flask backend is running"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
