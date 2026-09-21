import numpy as np


def _kmeans(points: np.ndarray, k: int, iters: int = 25, seed: int = 0) -> tuple:
    rng = np.random.default_rng(seed)
    if len(points) < k:
        return np.zeros((k, 2)), np.zeros(len(points), dtype=int)
    idx = rng.choice(len(points), k, replace=False)
    centers = points[idx].copy()
    labels = np.zeros(len(points), dtype=int)
    for _ in range(iters):
        dists = np.linalg.norm(points[:, None, :] - centers[None, :, :], axis=2)
        labels = np.argmin(dists, axis=1)
        for c in range(k):
            members = points[labels == c]
            if len(members):
                centers[c] = members.mean(axis=0)
    return centers, labels


def constellation_features(symbols: np.ndarray, candidate_orders: tuple = (2, 4, 8, 16)) -> dict:
    """Cluster symbol points and report the best-fit constellation order plus
    compactness (lower = tighter clusters = more confident match), i.e. an
    EVM-like metric computed from real clustering, not a hardcoded guess."""
    points = np.stack([symbols.real, symbols.imag], axis=1)
    if len(points) < 4:
        return {"best_order": 2, "compactness": 1.0, "cluster_count": 0}

    best_order, best_score, best_compactness = 2, -np.inf, 1.0
    for k in candidate_orders:
        centers, labels = _kmeans(points, k)
        # average intra-cluster distance normalized by inter-cluster spacing
        intra = np.mean([
            np.mean(np.linalg.norm(points[labels == c] - centers[c], axis=1))
            for c in range(k) if np.any(labels == c)
        ]) if k <= len(points) else np.inf
        center_dists = np.linalg.norm(centers[:, None, :] - centers[None, :, :], axis=2)
        np.fill_diagonal(center_dists, np.inf)
        min_center_dist = np.min(center_dists) if k > 1 else 1.0
        compactness = float(intra / (min_center_dist + 1e-9))
        score = -compactness  # tighter clusters -> better score
        if score > best_score:
            best_order, best_score, best_compactness = k, score, compactness

    return {"best_order": best_order, "compactness": best_compactness, "cluster_count": best_order}
