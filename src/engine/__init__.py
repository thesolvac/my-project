"""
APME Engine Package
===================
Exposes the top-level search API so callers only need:

    from src.engine import APMEEngine
"""

from .apme import APMEEngine, SearchResult, Match
from .heuristics import Algorithm, HeuristicResult, select_algorithm

__all__ = [
    "APMEEngine",
    "SearchResult",
    "Match",
    "Algorithm",
    "HeuristicResult",
    "select_algorithm",
]
