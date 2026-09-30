"""Ask questions about a project.

A small loop: the model either calls one of the tools in `agent/tools.py` or gives a
final answer. Tool results are appended to the transcript and fed back, so it can read
one file, then follow an import, then answer.

The loop reuses the existing `complete_json` client, so it works with any
OpenAI-compatible provider and needs no vendor-specific tool-calling support.
"""

import json
from collections.abc import Callable

from app.ai import AIError
from app.ai.client import LLMClient
from app.ai.json_stream import complete_streaming
from app.agent.tools import DESCRIPTIONS, TOOLS
from app.config.settings import Settings, get_settings
from app.models import CodeMap, Repository
from app.utils.logging import get_logger

logger = get_logger(__name__)

MAX_STEPS = 20


SYSTEM_PROMPT = f"""You are a security engineer answering questions about a codebase you \
can explore one step at a time.

Available tools:
{DESCRIPTIONS}

Reply with a single JSON object, and nothing else. Either call one tool:

    {{"tool": "read_file", "args": {{"path": "routes/search.py"}}, "why": "the route handler"}}

or give your final answer:

    {{"answer": "..."}}

Work from what the tools show you. Do not guess at file contents, and do not describe code \
you have not read. Cite files and line numbers. If the project does not contain what the \
question assumes, say so plainly rather than inventing it.

Answer as soon as you have enough evidence; you have a limited number of steps."""

LAST_STEP = (
    "\n\nThis is your final step. Answer now with what you have found, and say plainly "
    "which parts you could not verify."
)


def ask(
    client: LLMClient,
    repository: Repository,
    code_map: CodeMap,
    question: str,
    transcript: list[str] | None = None,
    on_step: Callable[[str, dict, str], None] | None = None,
    on_token: Callable[[str], None] | None = None,
    max_steps: int = MAX_STEPS,
    settings: Settings | None = None,
) -> tuple[str, list[str]]:
    """Answer `question`. Returns the answer and the updated transcript.

    Passing a previous transcript back in continues the conversation. `on_step` is
    called with (tool, args, why) as each tool runs, so a UI can show progress.
    `on_token` receives the final answer in pieces as the model writes it.
    """
    settings = settings or get_settings()
    history = list(transcript or [])
    history.append(f"QUESTION: {question}")

    for step in range(max_steps):
        prompt = "\n\n".join(history)
        # On the last step, ask for an answer rather than another tool call, so a long
        # investigation ends with findings instead of nothing.
        if step == max_steps - 1:
            prompt += LAST_STEP
        try:
            reply = complete_streaming(client, SYSTEM_PROMPT, prompt, "answer", on_token)
        except AIError as exc:
            return f"The model could not be reached: {exc}", history

        if "answer" in reply:
            answer = str(reply["answer"]).strip()
            history.append(f"ANSWER: {answer}")
            return answer, history

        name = reply.get("tool")
        tool = TOOLS.get(name)
        if not tool:
            history.append(f"ERROR: no tool named {name!r}. Use one of: {', '.join(TOOLS)}")
            continue

        args = reply.get("args") or {}
        if on_step:
            on_step(name, args, str(reply.get("why", "")))
        else:
            logger.info("step %d: %s(%s)", step + 1, name, json.dumps(args))
        result = tool(repository=repository, code_map=code_map, settings=settings, **args)
        history.append(f"CALLED {name}({json.dumps(args)}):\n{result}")

    return "I could not reach an answer within the step limit.", history
