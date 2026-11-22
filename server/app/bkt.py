from __future__ import annotations

P_INIT = 0.4
P_LEARN = 0.15
P_SLIP = 0.10
P_GUESS = 0.20


def update_mastery(
    state: dict[str, float],
    kc: str,
    correct: bool,
    *,
    p_learn: float = P_LEARN,
    p_slip: float = P_SLIP,
    p_guess: float = P_GUESS,
) -> dict[str, float]:
    """One BKT update for a single knowledge component."""
    p = float(state.get(kc, P_INIT))
    if correct:
        posterior = (p * (1 - p_slip)) / max(1e-9, p * (1 - p_slip) + (1 - p) * p_guess)
    else:
        posterior = (p * p_slip) / max(1e-9, p * p_slip + (1 - p) * (1 - p_guess))
    learned = posterior + (1 - posterior) * p_learn
    state[kc] = round(min(0.99, max(0.01, learned)), 3)
    return state


def infer_correct(text: str, misconception: str = "") -> bool:
    """Demo heuristic: a response that repeats the target misconception is incorrect."""
    text = (text or "").strip()
    if not text:
        return False
    if misconception and misconception in text:
        return False
    correct_markers = [
        "경험", "마음", "사람마다", "소중한 이유", "함께한",
        "생각", "의도", "가치", "중요",
    ]
    return any(marker in text for marker in correct_markers)
