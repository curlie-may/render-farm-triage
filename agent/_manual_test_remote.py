"""One-off verification: run the deployed Cloud Run agent over HTTPS.

Not part of the deliverable. Hits the same ADK api_server HTTP surface a
browser or judge would use (POST .../sessions, then POST /run_sse for the
SSE event stream), rather than the in-process Runner _manual_test.py uses for
local testing. Mirrors _manual_test.py's transcript format exactly by reusing
google.adk.events.event.Event to parse each SSE payload, so the two are
directly diffable.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from google.adk.events.event import Event

_TRANSCRIPTS_DIR = Path(__file__).resolve().parent / "transcripts"


class _Tee:
  def __init__(self, *streams):
    self._streams = streams

  def write(self, data):
    for stream in self._streams:
      stream.write(data)

  def flush(self):
    for stream in self._streams:
      stream.flush()


def main(base_url: str) -> None:
  app_name = "agent"
  user_id = "test_user"

  t0 = time.monotonic()
  print(f"[{datetime.now().isoformat()}] Creating session against {base_url} ...")

  resp = requests.post(
      f"{base_url}/apps/{app_name}/users/{user_id}/sessions",
      json={},
      timeout=120,
  )
  resp.raise_for_status()
  session = resp.json()
  session_id = session["id"]
  t_session_created = time.monotonic()
  print(
      f"[{datetime.now().isoformat()}] Session {session_id} created in"
      f" {t_session_created - t0:.2f}s (this call makes no LLM/tool calls, so"
      " its latency is dominated by container cold start, if any)."
  )

  payload = {
      "app_name": app_name,
      "user_id": user_id,
      "session_id": session_id,
      "new_message": {
          "role": "user",
          "parts": [{"text": "Triage last night's batch."}],
      },
      "streaming": False,
  }

  t_request_sent = time.monotonic()
  first_byte_time = None

  with requests.post(
      f"{base_url}/run_sse",
      json=payload,
      stream=True,
      timeout=590,
  ) as resp:
    resp.raise_for_status()
    for line in resp.iter_lines(decode_unicode=True):
      if first_byte_time is None:
        first_byte_time = time.monotonic()
        print(
            f"[{datetime.now().isoformat()}] First byte of /run_sse response"
            f" after {first_byte_time - t_request_sent:.2f}s."
        )
      if not line or not line.startswith("data:"):
        continue
      data = line[len("data:"):].strip()
      if not data:
        continue
      event_data = json.loads(data)
      if isinstance(event_data, dict) and "error" in event_data and "author" not in event_data:
        print(f"\n=== SERVER ERROR ===\n{event_data}")
        continue
      event = Event.model_validate(event_data)
      author = event.author
      if event.get_function_calls():
        for fc in event.get_function_calls():
          print(f"\n=== TOOL CALL ({author}): {fc.name} ===")
          print(f"args: {fc.args}")
      if event.get_function_responses():
        for fr in event.get_function_responses():
          print(f"\n=== TOOL RESPONSE ({author}): {fr.name} ===")
          print(f"response: {fr.response}")
      if event.content and event.content.parts:
        for part in event.content.parts:
          if part.text:
            print(f"\n=== TEXT ({author}) ===")
            print(part.text)

  t_end = time.monotonic()
  print(f"\n[{datetime.now().isoformat()}] Stream complete.")
  print(f"Session creation: {t_session_created - t0:.2f}s")
  print(f"Time to first SSE byte: {(first_byte_time - t_request_sent) if first_byte_time else float('nan'):.2f}s")
  print(f"Total wall-clock (session create + run): {t_end - t0:.2f}s")


if __name__ == "__main__":
  if len(sys.argv) != 2:
    print("Usage: python -m agent._manual_test_remote <base_url>")
    sys.exit(1)

  _TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
  run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
  transcript_path = _TRANSCRIPTS_DIR / f"run_{run_id}.txt"

  with open(transcript_path, "w", encoding="utf-8") as f:
    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, f)
    try:
      main(sys.argv[1].rstrip("/"))
    finally:
      sys.stdout = original_stdout

  print(f"\nTranscript written to {transcript_path}")
