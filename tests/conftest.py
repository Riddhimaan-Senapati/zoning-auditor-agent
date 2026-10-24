from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from smolagents.models import (
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    Model,
    TokenUsage,
)

from auditor import agents
from auditor.agents import CachedModel, Settings

MINI53 = Path(__file__).parent / "fixtures" / "mini53"


def reply(content: str = '{"ok": true}', cost: object = "0.0012") -> ChatMessage:
    return ChatMessage(role="assistant", content=content, raw=SimpleNamespace(usage=SimpleNamespace(cost=cost)),
                       token_usage=TokenUsage(input_tokens=11, output_tokens=7))


def call(name: str, arguments: dict, cost: str = "0.0005") -> ChatMessage:
    tool_call = ChatMessageToolCall(function=ChatMessageToolCallFunction(name=name, arguments=arguments),
                                    id=f"call-{name}", type="function")
    return ChatMessage(role="assistant", content=None, tool_calls=[tool_call],
                       raw=SimpleNamespace(usage=SimpleNamespace(cost=cost)),
                       token_usage=TokenUsage(input_tokens=9, output_tokens=3))


class FakeModel(Model):
    """Stands in for OpenRouter: returns the scripted messages in order, else `reply()`."""

    def __init__(self, scripted: list[ChatMessage] = (), cost: object = "0.0012"):
        super().__init__(model_id="fake/model")
        self.scripted = list(scripted)
        self.cost = cost
        self.calls = 0

    def generate(self, messages, stop_sequences=None, response_format=None, tools_to_call_from=None, **kwargs):
        self.calls += 1
        return self.scripted.pop(0) if self.scripted else reply(cost=self.cost)


def settings(tmp: Path, *, offline: bool = False, per_run: str = "20", total: str = "100") -> Settings:
    return Settings(api_key="unused", model_judge="judge/m", model_extract="extract/m", offline=offline,
                    budget_usd=Decimal(per_run), budget_total_usd=Decimal(total),
                    runs_root=tmp / "runs", cache_dir=tmp / "llm_cache")


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs" / "current" / "r1"


@pytest.fixture
def script(monkeypatch, tmp_path):
    """Route run_agent's model through CachedModel over a FakeModel; tools stay the real MCP server."""

    def install(*scripted: ChatMessage, **over) -> FakeModel:
        inner = FakeModel(scripted)
        s = settings(tmp_path, **over)
        monkeypatch.setattr(agents, "make_model",
                            lambda role, run_dir: CachedModel(inner, role=role, settings=s, run_dir=run_dir))
        return inner

    return install
