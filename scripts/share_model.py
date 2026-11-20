"""How the share of each theme changes over time: a multinomial logistic regression with a natural cubic spline in year.

Each paper is one observation: which of the K themes it belongs to. The model gives every year a share per theme
(the shares add up to 100%), years with more papers weigh more, the fitted shares stay between 0 and 100%, and the
spline lets a theme rise and level off. Uncertainty: the coefficients are drawn many times from their estimated
sampling distribution (normal, with the inverse of the observed information as covariance), and each draw gives a set
of curves; the 2.5th and 97.5th percentiles of those curves are the 95% bands.

Only numpy is needed. Because all papers of one year have the same predictors, the model is fitted on the counts per
year and theme (this gives exactly the same estimates as fitting paper by paper).
"""
import numpy as np


def natural_spline_basis(x, knots):
    """Natural cubic spline basis without the intercept (Hastie, Tibshirani & Friedman, The Elements of Statistical
    Learning, eq. 5.4-5.5): x, then d_k(x) - d_{M-1}(x) for k = 1 .. M-2, with
    d_k(x) = ((x - knot_k)^3_+ - (x - knot_M)^3_+) / (knot_M - knot_k). Linear beyond the outer knots."""
    x = np.asarray(x, float)
    k = np.asarray(knots, float)
    M = len(k)
    cols = [x]
    def d(j):
        return (np.clip(x - k[j], 0, None) ** 3 - np.clip(x - k[M - 1], 0, None) ** 3) / (k[M - 1] - k[j])
    for j in range(M - 2):
        cols.append(d(j) - d(M - 2))
    return np.column_stack(cols)


def design(x, knots):
    """intercept plus spline basis; x is rescaled to 0..1 over the outer knots, for numerical stability"""
    lo, hi = knots[0], knots[-1]
    z = (np.asarray(x, float) - lo) / (hi - lo)
    kz = (np.asarray(knots, float) - lo) / (hi - lo)
    if len(knots) == 2:
        return np.column_stack([np.ones_like(z), z])
    return np.column_stack([np.ones_like(z), natural_spline_basis(z, kz)])


def _probs(X, B):
    eta = X @ B
    eta -= eta.max(axis=1, keepdims=True)
    e = np.exp(eta)
    return e / e.sum(axis=1, keepdims=True)


def shares(X, B):
    """fitted shares (rows of X x categories) for coefficients B"""
    return _probs(X, B)


def fit_multinomial(X, N, ref, max_iter=100, tol=1e-10):
    """Maximum likelihood for counts N (rows: groups with design row X, columns: categories), category ref as
    reference (its coefficients are 0). Newton-Raphson with step halving.
    Returns the coefficients B (D x K), their covariance (for the free coefficients, in the order of free_index)
    and the log likelihood."""
    G, D = X.shape
    K = N.shape[1]
    free = [k for k in range(K) if k != ref]
    n = N.sum(axis=1)
    B = np.zeros((D, K))
    def loglik(B):
        P = _probs(X, B)
        return float((N * np.log(np.clip(P, 1e-300, None))).sum())
    ll = loglik(B)
    for _ in range(max_iter):
        P = _probs(X, B)
        grad = np.concatenate([X.T @ (N[:, k] - n * P[:, k]) for k in free])
        H = np.zeros((len(free) * D, len(free) * D))
        for a, k in enumerate(free):
            for b, l in enumerate(free):
                w = n * P[:, k] * ((k == l) - P[:, l])
                H[a * D:(a + 1) * D, b * D:(b + 1) * D] = -(X.T * w) @ X
        step = np.linalg.solve(-H, grad)
        t = 1.0
        while True:
            Bn = B.copy()
            for a, k in enumerate(free):
                Bn[:, k] += t * step[a * D:(a + 1) * D]
            lln = loglik(Bn)
            if lln >= ll - 1e-12 or t < 1e-6:
                break
            t /= 2
        B, done = Bn, abs(lln - ll) < tol
        ll = lln
        if done:
            break
    P = _probs(X, B)
    H = np.zeros((len(free) * D, len(free) * D))
    for a, k in enumerate(free):
        for b, l in enumerate(free):
            w = n * P[:, k] * ((k == l) - P[:, l])
            H[a * D:(a + 1) * D, b * D:(b + 1) * D] = -(X.T * w) @ X
    cov = np.linalg.inv(-H)
    return B, cov, ll, free


def dispersion(X, N, B, n_params):
    """Pearson chi-square divided by its degrees of freedom (cells minus the fixed group totals minus parameters).
    Above 1 means the counts vary more from group to group than a multinomial model allows (for papers: one project
    often brings several papers on one theme in one year). Multiplying the covariance by this factor widens the
    intervals accordingly (quasi-likelihood)."""
    n = N.sum(axis=1, keepdims=True)
    E = n * _probs(X, B)
    ok = E > 0
    x2 = float((((N - E) ** 2)[ok] / E[ok]).sum())
    return x2 / (N.size - N.shape[0] - n_params)


def knots_for(df, years, weights):
    """df + 1 knots: the first and last year, and df - 1 inner knots at equally spaced quantiles of the papers' years"""
    years = np.asarray(years, float)
    w = np.asarray(weights, float)
    cw = np.cumsum(w) / w.sum()
    inner = [float(np.interp(q, cw, years)) for q in np.linspace(0, 1, df + 1)[1:-1]]
    return [float(years[0])] + inner + [float(years[-1])]


def draws_of_shares(B, cov, free, Xgrid, n_draws=4000, seed=1):
    """shares (draws x grid points x K) for coefficient draws from N(B, cov)"""
    rng = np.random.default_rng(seed)
    D = B.shape[0]
    flat = np.concatenate([B[:, k] for k in free])
    S = rng.multivariate_normal(flat, cov, size=n_draws, method="cholesky")
    out = np.empty((n_draws, Xgrid.shape[0], B.shape[1]))
    for i in range(n_draws):
        Bi = np.zeros_like(B)
        for a, k in enumerate(free):
            Bi[:, k] = S[i, a * D:(a + 1) * D]
        out[i] = _probs(Xgrid, Bi)
    return out
