def score_square(score):
    """Map a 0-100 score to a coloured square for shareable, spoiler-free results."""
    if score >= 90:
        return "🟩"
    if score >= 60:
        return "🟨"
    if score >= 25:
        return "🟧"
    return "🟥"


def share_text(puzzle_date, score, distance_km, exact):
    """Build a Wordle-style shareable line that reveals the result but not the country."""
    detail = "🎯 exact!" if exact else f"{round(distance_km)} km off"
    return f"🌍 Countrydle {puzzle_date}\n{score_square(score)} {score}/100 · {detail}"
