from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# MongoDB setup
client = MongoClient(os.getenv("MONGO_URI"))
db = client["webhookDB"]
events_collection = db["events"]

# Helper to parse GitHub payloads
def parse_event(event_type, payload):
    if event_type == "push":
        return {
            "author": payload["pusher"]["name"],
            "action": "PUSH",
            "from_branch": None,
            "to_branch": payload["ref"].split("/")[-1],
            "timestamp": datetime.utcnow()
        }
    elif event_type == "pull_request":
        pr = payload["pull_request"]
        return {
            "author": pr["user"]["login"],
            "action": "PULL_REQUEST",
            "from_branch": pr["head"]["ref"],
            "to_branch": pr["base"]["ref"],
            "timestamp": datetime.utcnow()
        }
    elif event_type == "merge":
        # NOTE: GitHub doesn't send "merge" events directly.
        # You can treat "pull_request" with merged == true
        return None
    else:
        return None

# Webhook receiver
@app.route("/webhook", methods=["POST"])
def webhook():
    event_type = request.headers.get("X-GitHub-Event")
    payload = request.get_json()

    if event_type == "pull_request":
        if payload["action"] == "closed" and payload["pull_request"]["merged"]:
            doc = {
                "author": payload["pull_request"]["user"]["login"],
                "action": "MERGE",
                "from_branch": payload["pull_request"]["head"]["ref"],
                "to_branch": payload["pull_request"]["base"]["ref"],
                "timestamp": datetime.utcnow()
            }
        else:
            doc = parse_event(event_type, payload)
    else:
        doc = parse_event(event_type, payload)

    if doc:
        events_collection.insert_one(doc)
        return jsonify({"status": "saved"}), 201
    else:
        return jsonify({"status": "ignored"}), 200

# Serve events for UI polling
@app.route("/events", methods=["GET"])
def get_events():
    results = events_collection.find().sort("timestamp", -1).limit(20)
    output = []
    for event in results:
        timestamp = event["timestamp"].strftime("%d %b %Y - %H:%M UTC")
        if event["action"] == "PUSH":
            msg = f'{event["author"]} pushed to {event["to_branch"]} on {timestamp}'
        elif event["action"] == "PULL_REQUEST":
            msg = f'{event["author"]} submitted a pull request from {event["from_branch"]} to {event["to_branch"]} on {timestamp}'
        elif event["action"] == "MERGE":
            msg = f'{event["author"]} merged branch {event["from_branch"]} to {event["to_branch"]} on {timestamp}'
        else:
            msg = "Unknown event"
        output.append(msg)
    return jsonify(output)

# Minimal UI
@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
