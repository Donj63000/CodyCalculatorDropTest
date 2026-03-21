"""Utilities for Python differential testing."""

from importlib import import_module

__all__ = [
    "DifferentialConfig",
    "DifferentialOutcome",
    "FunctionCandidate",
    "run_differential_analysis",
]


def __getattr__(name: str):
    if name in __all__:
        module = import_module("specfence_py.differential")
        return getattr(module, name)
    raise AttributeError(name)
