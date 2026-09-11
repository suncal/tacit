"""Brains produce two things: agent turns (tool calls + text) and drafts (what a human would have written).

    anthropic         official SDK, Claude Opus 5, native tool use, adaptive thinking
    claude-cli        the `claude` CLI subscription you already have
    openai-compatible any OpenAI-style endpoint
    local             deterministic; no model. Same harness, literal answers, nearest-example drafts.
"""
from .base import Brain, BrainError, Turn
from .local import LocalBrain


def make_brain(settings) -> Brain:
    import os
    import shutil
    p = settings.brain_provider
    if p == "auto":
        if settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or os.path.exists(os.path.expanduser("~/.config/anthropic")):
            p = "anthropic"
        elif settings.brain_base_url:
            p = "openai-compatible"
        elif os.environ.get("TACIT_USE_CLAUDE_CLI") and shutil.which("claude"):
            p = "claude-cli"
        else:
            p = "local"
    if p == "anthropic":
        from .anthropic_ import AnthropicBrain
        return AnthropicBrain(settings.brain_model, settings.brain_effort, settings.anthropic_api_key or None)
    if p == "claude-cli":
        from .claude_cli import ClaudeCLIBrain
        return ClaudeCLIBrain("opus" if "opus" in settings.brain_model else settings.brain_model)
    if p == "openai-compatible":
        from .openai_compat import OpenAICompatBrain
        return OpenAICompatBrain(settings.brain_base_url, settings.brain_model)
    return LocalBrain()
