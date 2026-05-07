"""
Pattern Fitness — Layer 4 of the AI-native pattern strategy system.

Learns the edge (mean forward return) of every (pattern × timeframe × regime)
combination from historical signals, with:
  - Bayesian credibility intervals (n-aware)
  - Min sample threshold (cells with n < min_samples are inactive)
  - Multiple-testing correction via Benjamini-Hochberg FDR

Output: FitnessTensor — a dict of FitnessCell keyed by (pattern, tf, cell_id, direction).

The composer (Layer 5) reads this tensor + current regime + current active signals
to produce a weighted ensemble decision.

See .claude/plans/pattern_strategy_master.json (architecture.layer_4_fitness_tensor)
for the design philosophy.
"""
from .types import FitnessCell, FitnessTensor, FitnessTensorMeta
from .forward_returns import attach_forward_returns
from .learner import FitnessLearner
from .cross_symbol_learner import CrossSymbolFitnessLearner

__all__ = [
    "FitnessCell",
    "FitnessTensor",
    "FitnessTensorMeta",
    "attach_forward_returns",
    "FitnessLearner",
    "CrossSymbolFitnessLearner",
]
