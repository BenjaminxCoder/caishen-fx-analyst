### 
# import os: loads Python's built-in Operating System module
# import json: loads Python's built-in JSON (JavaScript Object Notation) module.
# import requests: loads the popular third-party Requests library into your script;
#   enabling your code to send HTTP requests and interact with websites or APIs. 
# from dotenv import load_dotenv: Let's us keep our API keys or Tokens safe from leaking.
###
import os
import json
import requests
from dotenv import load_dotenv

# 1. Load environment variables from your local .env file
load_dotenv()

API_TOKEN = os.getenv("OANDA_API_TOKEN")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
STREAM_URL = os.getenv("OANDA_STREAM_URL")

url = f"{STREAM_URL}/v3/accounts/{ACCOUNT_ID}/transactions/stream"
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
}

def start_stream():
    print(f"Connecting to OANDA stream for {ACCOUNT_ID}...")

    # timeout=(10, 30) means: wait up to 10s to connect and 30s between incoming data chuncks
    with requests.get(url, headers=headers, stream=True, timeout=(10, 30)) as response:
        response.raise_for_status()
        print("Stream active! Waiting for heartbeats and trades (Ctrl+C to exit)...\n")

        for raw_line in response.iter_lines():
            if raw_line:
                event = json.loads(raw_line.decode("utf-8"))
                event_type = event.get("type")

                if event_type == "HEARTBEAT":
                    print(f"[HEARTBEAT] {event.get('time')}")
                else:
                    print(f"\n>>> TRANSACTION EVENT: {event_type} <<<")
                    print(json.dumps(event, indent=2))

if __name__ == "__main__":
    try:
        start_stream()
    except KeyboardInterrupt:
        print("\nStream Stopped cleanly.")