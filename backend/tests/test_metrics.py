from koherent.pipeline.metrics import hit_at_k, reciprocal_rank


def test_hit_at_k_true_within_k():
    ranked = ["nothing here", "Elasticity measures responsiveness", "other"]
    assert hit_at_k(ranked, "elasticity", k=2) is True


def test_hit_at_k_false_outside_k():
    ranked = ["nothing here", "still nothing", "Elasticity measures"]
    assert hit_at_k(ranked, "elasticity", k=2) is False


def test_reciprocal_rank_of_first_match():
    ranked = ["miss", "miss", "Elasticity here"]
    assert reciprocal_rank(ranked, "elasticity") == 1 / 3


def test_reciprocal_rank_no_match_is_zero():
    assert reciprocal_rank(["a", "b"], "zzz") == 0.0
