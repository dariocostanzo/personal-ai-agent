"""Small explicit-command registry for locally available agent capabilities."""

from dataclasses import dataclass
from typing import Callable, Optional, Tuple


Command = Tuple
Matcher = Callable[[str], Optional[Command]]
Handler = Callable[[Command], object]


@dataclass(frozen=True)
class Capability:
    name: str
    matcher: Matcher
    handler: Handler


class CapabilityRouter:
    def __init__(self):
        self._capabilities = []

    def register(self, name, matcher, handler):
        if any(capability.name == name for capability in self._capabilities):
            raise ValueError(f"Capability already registered: {name}")
        self._capabilities.append(Capability(name, matcher, handler))

    def dispatch(self, prompt):
        for capability in self._capabilities:
            command = capability.matcher(prompt)
            if command is not None:
                return capability.name, capability.handler(command)
        return None, None

    @property
    def capabilities(self):
        return tuple(capability.name for capability in self._capabilities)
