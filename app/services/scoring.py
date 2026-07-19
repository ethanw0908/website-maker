from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreResult:
    score: int
    reasons: list[str]


def score_lead(*, has_website: bool, reachable: bool = True, mobile_responsive: bool = True,
               outdated_visual_signals: bool = False, has_call_to_action: bool = True,
               has_service_information: bool = True, rating: float | None = None,
               review_count: int = 0, is_large_chain: bool = False,
               has_public_contact: bool = True, recently_redesigned: bool = False) -> ScoreResult:
    score = 0
    reasons: list[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(f"{points:+d}: {reason}")

    if not has_website:
        add(40, "No website")
    else:
        if not reachable:
            add(30, "Website is broken or inaccessible")
        if not mobile_responsive:
            add(25, "Website is not mobile responsive")
        if outdated_visual_signals:
            add(15, "Website shows outdated visual patterns")
        if not has_call_to_action:
            add(10, "No obvious call to action")
        if not has_service_information:
            add(10, "Missing service information")
        if recently_redesigned:
            add(-40, "Recently redesigned professional website")

    if rating is not None and rating >= 4.2 and review_count >= 25:
        add(15, "Strong rating and meaningful review volume")
    if is_large_chain:
        add(-30, "Large franchise or corporate chain")
    if not has_public_contact:
        add(-15, "No public contact method")

    return ScoreResult(score=score, reasons=reasons)
