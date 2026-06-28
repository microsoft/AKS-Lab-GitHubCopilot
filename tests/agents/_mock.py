"""Mock chat client for agent unit tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, cast


@dataclass(frozen=True)
class MockAgentResponse:
    """Minimal response shape consumed by specialist adapters."""

    text: str


class MockChatClient:
    """ClassVar-capturing fake for GitHubCopilotAgent."""

    captured_kwargs: ClassVar[dict[str, object] | None] = None
    responses: ClassVar[list[str]] = []
    errors: ClassVar[list[Exception]] = []
    messages: ClassVar[list[str]] = []

    def __init__(self, **kwargs: object) -> None:
        self.__class__.captured_kwargs = kwargs

    @classmethod
    def reset(cls, *, responses: Sequence[str] = (), errors: Sequence[Exception] = ()) -> None:
        cls.captured_kwargs = None
        cls.responses = list(responses)
        cls.errors = list(errors)
        cls.messages = []

    async def run(self, message: str) -> MockAgentResponse:
        self.__class__.messages.append(message)
        if self.__class__.errors:
            raise self.__class__.errors.pop(0)
        if self.__class__.responses:
            return MockAgentResponse(text=self.__class__.responses.pop(0))
        return MockAgentResponse(text="{}")


def captured_options() -> Mapping[str, object]:
    """Return captured default options as a mapping."""

    kwargs = MockChatClient.captured_kwargs
    if kwargs is None:
        raise AssertionError("GitHubCopilotAgent was not constructed")
    options = kwargs.get("default_options")
    if not isinstance(options, Mapping):
        options_dict = getattr(options, "__dict__", None)
        if not isinstance(options_dict, Mapping):
            raise AssertionError("default_options was not captured")
        return cast("Mapping[str, object]", options_dict)
    return cast("Mapping[str, object]", options)
