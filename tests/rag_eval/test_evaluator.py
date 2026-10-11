from uuid import uuid4
from app.analytics.metrics import compute_retrieval_metrics


def test_retrieval_metrics():
    expected = str(uuid4())
    metrics = compute_retrieval_metrics([(['other', expected], expected)])
    assert metrics.hit_rate == 1.0
    assert metrics.mean_reciprocal_rank == 0.5
