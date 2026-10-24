from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal, TypeVar

from mcp import StdioServerParameters
from pydantic import BaseModel, ConfigDict, ValidationError
from smolagents import ToolCallingAgent, ToolCollection
from smolagents.agents import ToolOutput
from smolagents.memory import FinalAnswerStep
from smolagents.models import (
    ChatMessage,
    Model,
    OpenAIModel,
    TokenUsage,
    get_clean_message_list,
    get_tool_json_schema,
    tool_role_conversions,
)
from smolagents.utils import AgentGenerationError

from auditor.models import TraceEvent

PROMPTS = Path(__file__).parent / "prompts"
REPO = Path(__file__).resolve().parents[2]
TRACE_OUTPUT_CAP = 2000
SPEND_EVERY = 25

ROLE_TIER: dict[str, Literal["judge", "extract"]] = {
    "extract_prose": "extract",
    "compare_match": "extract",
    "find_contradiction": "judge",
    "find_ambiguity": "judge",
    "judge_xref": "judge",
    "skeptic_contradiction": "judge",
    "skeptic_xref": "judge",
    "skeptic_ambiguity": "judge",
    "compare_support": "judge",
}


class BudgetExceeded(Exception):
    pass


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    api_key: str
    model_judge: str
    model_extract: str
    offline: bool
    budget_usd: Decimal
    budget_total_usd: Decimal
    runs_root: Path
    cache_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            api_key=os.environ["OPENROUTER_API_KEY"],
            model_judge=env("AUDITOR_MODEL_JUDGE", "anthropic/claude-sonnet-5.5"),
            model_extract=env("AUDITOR_MODEL_EXTRACT", "anthropic/claude-haiku-5.5"),
            offline=env("AUDITOR_OFFLINE") == "1",
            budget_usd=Decimal(env("AUDITOR_BUDGET_USD", "20")),
            budget_total_usd=Decimal(env("AUDITOR_BUDGET_TOTAL_USD", "100")),
            runs_root=Path(env("AUDITOR_RUNS_ROOT", REPO / "runs")),
            cache_dir=Path(env("AUDITOR_CACHE_DIR", REPO / "llm_cache")),
        )


class SpendLine(BaseModel):
    role: str
    model: str
    input_tokens: int
    output_tokens: int
    usd: Decimal
    cached: bool


class AgentFailure(BaseModel):
    role: str
    reason: str
    raw: str


def spend(ledgers: Iterable[Path]) -> Decimal:
    return sum(
        (
            SpendLine.model_validate_json(ln).usd
            for path in ledgers
            if path.exists()
            for ln in path.read_text().splitlines()
            if ln.strip()
        ),
        Decimal(0),
    )


def _read_cost(raw: object) -> Decimal:
    usage = getattr(raw, "usage", None)
    cost = usage.get("cost") if isinstance(usage, dict) else getattr(usage, "cost", None)
    if cost is None:
        raise RuntimeError("live response carries no usage.cost; OpenRouter cost is required")
    return Decimal(str(cost))


class CachedModel(Model):
    def __init__(self, inner: Model, *, role: str, settings: Settings, run_dir: Path):
        if not run_dir.resolve().is_relative_to(settings.runs_root.resolve()):
            raise ValueError(
                f"run dir {run_dir} is outside runs_root {settings.runs_root}, "
                "so the total spend cap could not see it"
            )
        super().__init__(model_id=inner.model_id)
        self.inner = inner
        self.role = role
        self.settings = settings
        self.run_dir = run_dir
        self.live_calls = 0
        # smolagents wraps or swallows anything generate() raises; run_agent re-raises this.
        self.error: Exception | None = None

    def spend_line(self) -> str:
        run = spend([self.run_dir / "spend.jsonl"])
        total = spend(self.settings.runs_root.glob("**/spend.jsonl"))
        return f"spend: ${run} this run, ${total} total, {self.live_calls} live {self.role} calls"

    def _log(self, usage: TokenUsage, usd: Decimal, cached: bool) -> None:
        line = SpendLine(role=self.role, model=self.model_id, input_tokens=usage.input_tokens,
                         output_tokens=usage.output_tokens, usd=usd, cached=cached)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with (self.run_dir / "spend.jsonl").open("a") as f:
            f.write(line.model_dump_json() + "\n")

    def generate(self, messages, stop_sequences=None, response_format=None,
                 tools_to_call_from=None, **kwargs) -> ChatMessage:
        if tools_to_call_from:
            # smolagents sends "required", which Anthropic models on OpenRouter reject (HTTP 400).
            kwargs.setdefault("tool_choice", "auto")
        try:
            return self._generate(messages, stop_sequences, response_format, tools_to_call_from, kwargs)
        except Exception as e:
            self.error = e
            raise

    def _generate(self, messages, stop_sequences, response_format, tools, kwargs) -> ChatMessage:
        blob = json.dumps({
            "model_id": self.model_id,
            "messages": get_clean_message_list(messages, role_conversions=tool_role_conversions),
            "tools": [get_tool_json_schema(t) for t in tools] if tools else None,
            "response_format": response_format,
            "stop": stop_sequences,
            "kwargs": kwargs,
        }, sort_keys=True, default=str)
        path = self.settings.cache_dir / f"{hashlib.sha256(blob.encode()).hexdigest()}.json"

        if path.exists():
            stored = json.loads(path.read_text())
            usage = TokenUsage(input_tokens=stored["input_tokens"], output_tokens=stored["output_tokens"])
            self._log(usage, Decimal(0), cached=True)
            return ChatMessage.from_dict(stored["message"], token_usage=usage)
        if self.settings.offline:
            raise RuntimeError(f"offline cache miss: role={self.role!r} key={path.stem}")

        caps = (
            ("per-run", spend([self.run_dir / "spend.jsonl"]), self.settings.budget_usd),
            ("total", spend(self.settings.runs_root.glob("**/spend.jsonl")), self.settings.budget_total_usd),
        )
        for name, spent, cap in caps:
            if spent >= cap:
                raise BudgetExceeded(f"{name} cap reached: ${spent} >= ${cap}")

        msg = self.inner.generate(messages, stop_sequences=stop_sequences, response_format=response_format,
                                  tools_to_call_from=tools, **kwargs)
        usd = _read_cost(msg.raw)
        usage = msg.token_usage or TokenUsage(input_tokens=0, output_tokens=0)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "message": json.loads(msg.model_dump_json()),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "usd": str(usd),
        }))
        os.replace(tmp, path)
        self._log(usage, usd, cached=False)
        self.live_calls += 1
        if self.live_calls % SPEND_EVERY == 0:
            print(self.spend_line(), file=sys.stderr)
        return msg


def make_model(role: str, run_dir: Path) -> CachedModel:
    settings = Settings.from_env()
    model_id = settings.model_judge if ROLE_TIER[role] == "judge" else settings.model_extract
    inner = OpenAIModel(model_id=model_id, api_base="https://openrouter.ai/api/v1", api_key=settings.api_key)
    return CachedModel(inner, role=role, settings=settings, run_dir=run_dir)


@contextmanager
def _mcp_tools(build_dir: Path):
    server = StdioServerParameters(command=sys.executable, args=["-m", "auditor.mcp_server", str(build_dir)])
    with ToolCollection.from_mcp(server, trust_remote_code=True, structured_output=False) as collection:
        yield collection


T = TypeVar("T", bound=BaseModel)


def run_agent(role: str, task: str, out: type[T], *, build_dir: Path, run_dir: Path,
              max_steps: int = 6) -> T | AgentFailure:
    model = make_model(role, run_dir)
    role_prompt = PROMPTS / f"{role}.md"
    instructions = (PROMPTS / "_preamble.md").read_text()
    if role_prompt.exists():
        instructions += "\n\n" + role_prompt.read_text()
    calls: list[dict] = []
    answer = None
    with _mcp_tools(build_dir) as collection:
        agent = ToolCallingAgent(tools=[*collection.tools], model=model, instructions=instructions)
        try:
            for event in agent.run(task, max_steps=max_steps, stream=True):
                if isinstance(event, ToolOutput):
                    calls.append({"name": event.tool_call.name, "arguments": event.tool_call.arguments,
                                  "output": event.observation[:TRACE_OUTPUT_CAP]})
                elif isinstance(event, FinalAnswerStep):
                    answer = event.output
        except AgentGenerationError as e:
            raise model.error or e
    if model.error is not None:
        raise model.error
    if model.live_calls:
        print(model.spend_line(), file=sys.stderr)

    event = TraceEvent(run_id=run_dir.name, candidate_id=hashlib.sha256(task.encode()).hexdigest()[:16],
                       stage=role, at=datetime.now(timezone.utc),
                       data={"task": task, "tool_calls": calls, "answer": str(answer)})
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "trace.jsonl").open("a") as f:
        f.write(event.model_dump_json() + "\n")

    try:
        if isinstance(answer, (dict, list)):
            return out.model_validate(answer)
        return out.model_validate_json(str(answer))
    except ValidationError as e:
        return AgentFailure(role=role, reason=str(e), raw=str(answer))
