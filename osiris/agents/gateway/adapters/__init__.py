"""Adapter package for cognitive substrates."""

from .replay import ReplayAdapter
from .antigravity import AntigravityAdapter
from .local_brain import LocalBrainAdapter

__all__ = ["ReplayAdapter", "AntigravityAdapter", "LocalBrainAdapter"]
