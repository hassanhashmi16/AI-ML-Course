"""Thin LiteLLM wrapper: one ask() call with fallbacks, retries, and cost."""

import logging
from typing import Optional

from litellm import Router, completion_cost

logger = logging.getLogger(__name__)

router = Router(
    model_list=[
        {"model_name": "primary", "litellm_params": {"model": "anthropic/claude-sonnet-5"}},
        {"model_name": "fallback", "litellm_params": {"model": "openai/gpt-4o"}},
    ],
    fallbacks={"primary": ["fallback"]},
    num_retries=3,
    timeout=30,
)


def ask(prompt: str, system: Optional[str] = None) -> str:
    """Call the primary model, falling back if it fails. Returns the text."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = router.completion(model="primary", messages=messages)
    cost = completion_cost(completion_response=response)
    logger.info("model=%s cost=$%.6f", response.model, cost)
    return response.choices[0].message.content
