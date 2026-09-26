import os

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("AGENT_MODEL", "gpt-4.1-mini")
TEMPERATURE = 0.0

# Investigation budget (tool calls), shared by both architectures for a fair comparison.
MAX_STEPS = 10

# Verifier hard rules (tuned on the development set only).
CONFIDENCE_THRESHOLD = 0.8
COMPETITOR_THRESHOLD = 0.5
MIN_SOURCE_TYPES = 2

# USD per 1M tokens (input, output). Update if pricing changes.
PRICING = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    for name, (inp, out) in PRICING.items():
        if model == name or model.startswith(name + "-20"):
            return (input_tokens * inp + output_tokens * out) / 1_000_000
    return None
