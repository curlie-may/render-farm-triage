"""One-off manual test: run the root agent through ADK's Runner directly.

Not part of the deliverable. Exercises the same code path `adk web` and
`adk run` use internally (a Runner over the root agent), so the transcript
this produces is representative of what `adk web` would show, without
needing a browser in this headless environment.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from google.adk.runners import InMemoryRunner
from google.genai import types

from agent.agent import root_agent

logging.basicConfig(level=logging.WARNING)

_TRANSCRIPTS_DIR = Path(__file__).resolve().parent / "transcripts"


class _Tee:
  """Writes to multiple streams at once (stdout + a transcript file)."""

  def __init__(self, *streams):
    self._streams = streams

  def write(self, data):
    for stream in self._streams:
      stream.write(data)

  def flush(self):
    for stream in self._streams:
      stream.flush()


async def main() -> None:
  runner = InMemoryRunner(agent=root_agent, app_name="render_farm_triage")
  session = await runner.session_service.create_session(
      app_name="render_farm_triage", user_id="test_user"
  )

  message = types.Content(
      role="user", parts=[types.Part(text="Triage last night's batch.")]
  )

  async for event in runner.run_async(
      user_id="test_user", session_id=session.id, new_message=message
  ):
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


if __name__ == "__main__":
  _TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
  run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
  transcript_path = _TRANSCRIPTS_DIR / f"run_{run_id}.txt"

  with open(transcript_path, "w", encoding="utf-8") as f:
    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, f)
    try:
      asyncio.run(main())
    finally:
      sys.stdout = original_stdout

  print(f"\nTranscript written to {transcript_path}")
