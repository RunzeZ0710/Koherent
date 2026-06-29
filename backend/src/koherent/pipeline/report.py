"""Pure report helpers, kept free of DB/HTTP so the threshold logic is unit-tested.

A note is an *anomaly* when it does not clearly correspond to anything the
lecture actually said: either it never aligned (no match) or its best match is
below the similarity threshold. This is the seed of cross-student misconception
detection (deferred): a note that matches nothing the professor said is exactly
what we want to surface.
"""


def is_anomaly(similarity: float | None, threshold: float) -> bool:
    return similarity is None or similarity < threshold
