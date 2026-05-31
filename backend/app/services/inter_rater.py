# Inter-Rater Agreement Calculator
# Cohen's Kappa, percent agreement, Fleiss' Kappa
from collections import Counter


def compute_inter_rater(
    rater1_codes: list[str],
    rater2_codes: list[str],
) -> dict:
    """Compute agreement metrics between two raters.

    Returns dict with percent_agreement, cohens_kappa, per_code_agreement.
    """
    if len(rater1_codes) != len(rater2_codes):
        raise ValueError(f"Rater code lists must be same length: {len(rater1_codes)} vs {len(rater2_codes)}")

    n = len(rater1_codes)
    if n == 0:
        return {
            "percent_agreement": 0.0,
            "cohens_kappa": 0.0,
            "n_pairs": 0,
            "per_code_agreement": {},
            "interpretation": "无数据",
        }

    # Percent agreement
    agreements = sum(1 for a, b in zip(rater1_codes, rater2_codes) if a == b)
    percent_agreement = agreements / n

    # Cohen's Kappa
    kappa = _cohen_kappa(rater1_codes, rater2_codes)

    # Per-code agreement
    per_code = {}
    all_codes = set(rater1_codes) | set(rater2_codes)
    for code in all_codes:
        r1_has = sum(1 for c in rater1_codes if c == code)
        r2_has = sum(1 for c in rater2_codes if c == code)
        per_code[code] = {
            "rater1_count": r1_has,
            "rater2_count": r2_has,
            "agreement": r1_has == r2_has,
        }

    # Interpretation
    if kappa >= 0.81:
        interpretation = "几乎完全一致 (Almost Perfect)"
    elif kappa >= 0.61:
        interpretation = "高度一致 (Substantial)"
    elif kappa >= 0.41:
        interpretation = "中等一致 (Moderate)"
    elif kappa >= 0.21:
        interpretation = "一般一致 (Fair)"
    elif kappa >= 0.0:
        interpretation = "轻微一致 (Slight)"
    else:
        interpretation = "一致性低于随机 (Poor)"

    return {
        "percent_agreement": round(percent_agreement, 4),
        "cohens_kappa": round(kappa, 4),
        "n_pairs": n,
        "per_code_agreement": per_code,
        "interpretation": interpretation,
    }


def _cohen_kappa(rater1: list[str], rater2: list[str]) -> float:
    """Compute Cohen's Kappa for two raters with nominal categories."""
    n = len(rater1)
    if n == 0:
        return 0.0

    categories = sorted(set(rater1) | set(rater2))
    cat_idx = {cat: i for i, cat in enumerate(categories)}
    k = len(categories)

    # Build observed agreement matrix
    observed = [[0] * k for _ in range(k)]
    for a, b in zip(rater1, rater2):
        observed[cat_idx[a]][cat_idx[b]] += 1

    # Observed agreement
    p_o = sum(observed[i][i] for i in range(k)) / n

    # Expected agreement
    row_sums = [sum(observed[i]) for i in range(k)]
    col_sums = [sum(observed[j][i] for j in range(k)) for i in range(k)]
    p_e = sum(row_sums[i] * col_sums[i] for i in range(k)) / (n * n)

    if p_e == 1.0:
        return 1.0

    return (p_o - p_e) / (1.0 - p_e)


def compute_multi_rater_agreement(
    rater_data: dict[str, list[str]],  # rater_id -> list of codes per case
) -> dict:
    """Compute agreement across multiple raters.

    Returns pairwise kappa matrix + Fleiss' Kappa approximation.
    """
    rater_ids = list(rater_data.keys())
    n_raters = len(rater_ids)

    if n_raters < 2:
        return {"error": "Need at least 2 raters", "n_raters": n_raters}

    # Check all raters have same number of cases
    n_cases = len(rater_data[rater_ids[0]])
    for rid in rater_ids:
        if len(rater_data[rid]) != n_cases:
            return {"error": f"Rater {rid} has {len(rater_data[rid])} cases, expected {n_cases}"}

    # Pairwise Kappa
    pairwise = {}
    for i in range(n_raters):
        for j in range(i + 1, n_raters):
            ri, rj = rater_ids[i], rater_ids[j]
            result = compute_inter_rater(rater_data[ri], rater_data[rj])
            pairwise[f"{ri}_vs_{rj}"] = {
                "cohens_kappa": result["cohens_kappa"],
                "percent_agreement": result["percent_agreement"],
            }

    # Average kappa
    avg_kappa = sum(p["cohens_kappa"] for p in pairwise.values()) / len(pairwise) if pairwise else 0.0
    avg_agreement = sum(p["percent_agreement"] for p in pairwise.values()) / len(pairwise) if pairwise else 0.0

    # Fleiss' Kappa (approximation for >2 raters)
    fleiss = _fleiss_kappa(rater_data)

    return {
        "n_raters": n_raters,
        "n_cases": n_cases,
        "pairwise_kappa": pairwise,
        "avg_cohens_kappa": round(avg_kappa, 4),
        "avg_percent_agreement": round(avg_agreement, 4),
        "fleiss_kappa": round(fleiss, 4) if fleiss is not None else None,
    }


def _fleiss_kappa(rater_data: dict[str, list[str]]) -> float | None:
    """Compute Fleiss' Kappa for multiple raters.

    Returns None if computation is not possible.
    """
    rater_ids = list(rater_data.keys())
    n_raters = len(rater_ids)
    if n_raters < 2:
        return None

    n_cases = len(rater_data[rater_ids[0]])

    # Collect all categories
    all_codes = set()
    for codes in rater_data.values():
        all_codes.update(codes)
    categories = sorted(all_codes)
    k = len(categories)
    if k <= 1:
        return 1.0  # Only one category → perfect agreement

    cat_idx = {cat: i for i, cat in enumerate(categories)}

    # Build n_ij matrix: for each case i, count raters who assigned category j
    n_ij = [[0] * k for _ in range(n_cases)]
    for case_idx in range(n_cases):
        for rid in rater_ids:
            code = rater_data[rid][case_idx]
            n_ij[case_idx][cat_idx[code]] += 1

    # Proportion of all assignments to category j
    p_j = [0.0] * k
    for j in range(k):
        total_j = sum(n_ij[i][j] for i in range(n_cases))
        p_j[j] = total_j / (n_cases * n_raters)

    # Per-case agreement
    P_i = [0.0] * n_cases
    for i in range(n_cases):
        total = sum(n_ij[i][j] * (n_ij[i][j] - 1) for j in range(k))
        P_i[i] = total / (n_raters * (n_raters - 1)) if n_raters > 1 else 0

    P_bar = sum(P_i) / n_cases
    P_e_bar = sum(p_j[j] ** 2 for j in range(k))

    if P_e_bar == 1.0:
        return 1.0

    return (P_bar - P_e_bar) / (1.0 - P_e_bar)
