"""Root agent definition for the render farm triage assistant.

Two toolsets are attached:

1. An OpenAPIToolset built from the project's own openapi.yaml, exposing the
   six fixed diagnostic tools deployed at
   https://render-farm-triage.vercel.app/api/tools. These carry the
   statistical logic (significance testing, base-rate comparison, retry
   dedupe) and are the agent's primary instruments.

2. An McpToolset connected to the official `mcp-clickhouse` MCP server over
   stdio, restricted to its read-only tools (run_query, list_tables,
   list_databases), for exploratory SQL the fixed tools don't cover. It is
   deliberately secondary — see instructions.py for how the agent is told to
   sequence the two.

Model: left unset. `LlmAgent` falls back to `LlmAgent.DEFAULT_MODEL` (a
current Gemini model, resolved from the installed google-adk package rather
than hardcoded here) when no model is set on the agent and there is no
ancestor to inherit one from, which is the case for this single, root agent.

On tool confirmation: ADK's `require_confirmation` (on FunctionTool/MCPTool,
and exposed on McpToolset's constructor) pauses and resumes a *single tool
call*, gated on the model re-sending the same function call with a
human-supplied ToolConfirmation. It does not model "approve this proposed
plan, with N independently editable steps" — that is a different shape of
approval entirely, and closer to a UI concern (see SPEC.md section 7's
Accept/Modify/Reject controls) than an agent-level tool gate. It also isn't
needed for what it does gate here: every tool this agent has, on both
toolsets, is read-only, so there is no destructive execution step to pause
before. `require_confirmation` is deliberately left at its default (off) on
the MCP toolset, and OpenAPIToolset does not expose the parameter at all in
the installed ADK version. See the task write-up for the fuller investigation.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset import (
    OpenAPIToolset,
)
from mcp import StdioServerParameters

from .instructions import INSTRUCTIONS

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OPENAPI_SPEC_PATH = _REPO_ROOT / "openapi.yaml"
_OPENAPI_SPEC_URL = "https://render-farm-triage.vercel.app/openapi.yaml"


def _load_openapi_spec() -> str:
  # Local dev: the full repo checkout has openapi.yaml as agent.py's sibling
  # at the repo root. Deployed (e.g. Cloud Run): only agent/ itself gets
  # shipped into the container, so that path doesn't exist there — fall back
  # to fetching the identical file from the one place it's actually served
  # from (see openapi.yaml's own header: same file, single source of truth).
  if _OPENAPI_SPEC_PATH.exists():
    return _OPENAPI_SPEC_PATH.read_text(encoding="utf-8")
  with urllib.request.urlopen(_OPENAPI_SPEC_URL, timeout=15) as response:
    return response.read().decode("utf-8")


def _build_diagnostic_toolset() -> OpenAPIToolset:
  spec_str = _load_openapi_spec()
  return OpenAPIToolset(spec_str=spec_str, spec_str_type="yaml")


def _build_clickhouse_toolset() -> McpToolset:
  # mcp-clickhouse reads these exact names; they're the same cluster the
  # deployed tools already use (see .env.example at the repo root).
  clickhouse_env = {
      key: os.environ[key]
      for key in (
          "CLICKHOUSE_HOST",
          "CLICKHOUSE_PORT",
          "CLICKHOUSE_USER",
          "CLICKHOUSE_PASSWORD",
          "CLICKHOUSE_DATABASE",
          "CLICKHOUSE_SECURE",
      )
      if key in os.environ
  }
  # Belt and suspenders: mcp-clickhouse already defaults to read-only
  # (CLICKHOUSE_ALLOW_WRITE_ACCESS=false), but pin it explicitly so a stray
  # variable in the parent environment can't loosen it for this agent.
  clickhouse_env["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "false"

  return McpToolset(
      connection_params=StdioConnectionParams(
          server_params=StdioServerParameters(
              command="mcp-clickhouse",
              args=[],
              env=clickhouse_env,
          ),
          timeout=30,
      ),
      tool_filter=["run_query", "list_tables", "list_databases"],
  )


root_agent = Agent(
    name="render_farm_triage_agent",
    description=(
        "Diagnoses overnight render farm batch failures across all jobs on a"
        " shared farm and proposes an ordered, human-approved re-queue plan."
    ),
    instruction=INSTRUCTIONS,
    tools=[_build_diagnostic_toolset(), _build_clickhouse_toolset()],
)
