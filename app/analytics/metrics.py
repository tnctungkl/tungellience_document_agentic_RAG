from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalMetrics:
    hit_rate: float
    mean_reciprocal_rank: float


def compute_retrieval_metrics(rows: list[tuple[list[str], str]]) -> RetrievalMetrics:
    """Compute simple, transparent retrieval metrics from ranked IDs."""
    if not rows:
        return RetrievalMetrics(0.0, 0.0)
    hits = 0
    reciprocal_sum = 0.0
    for ranked_ids, expected_id in rows:
        if expected_id in ranked_ids:
            hits += 1
            reciprocal_sum += 1 / (ranked_ids.index(expected_id) + 1)
    return RetrievalMetrics(hits / len(rows), reciprocal_sum / len(rows))
