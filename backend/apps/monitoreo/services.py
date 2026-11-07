from dataclasses import dataclass

from django.conf import settings

from apps.intentos.models import Incident


EVENT_WEIGHTS = {
    Incident.Kind.TAB_HIDDEN: int(getattr(settings, "PROCTOR_WEIGHT_TAB_HIDDEN", 12)),
    Incident.Kind.WINDOW_BLUR: int(getattr(settings, "PROCTOR_WEIGHT_WINDOW_BLUR", 8)),
    Incident.Kind.CAMERA_LOST: int(getattr(settings, "PROCTOR_WEIGHT_CAMERA_LOST", 20)),
    Incident.Kind.MICROPHONE_LOST: int(getattr(settings, "PROCTOR_WEIGHT_MICROPHONE_LOST", 20)),
    Incident.Kind.CAMERA_MUTED: int(getattr(settings, "PROCTOR_WEIGHT_CAMERA_MUTED", 14)),
    Incident.Kind.MICROPHONE_MUTED: int(getattr(settings, "PROCTOR_WEIGHT_MICROPHONE_MUTED", 14)),
}
MAX_DURATION_POINTS_PER_EVENT = 20
DURATION_POINTS_PER_30_SECONDS = 1


@dataclass(frozen=True)
class SuspicionAssessment:
    score: int
    level: str
    incident_count: int
    by_kind: dict[str, int]


def assess_attempt(attempt) -> SuspicionAssessment:
    """Score signals; this assessment never changes the academic grade."""
    score = 0
    counts = {}
    for incident in attempt.incidents.all():
        counts[incident.kind] = counts.get(incident.kind, 0) + 1
        points = EVENT_WEIGHTS[incident.kind]
        if incident.duration_ms:
            duration_points = min(
                MAX_DURATION_POINTS_PER_EVENT,
                incident.duration_ms // (30_000 * DURATION_POINTS_PER_30_SECONDS),
            )
            points += duration_points
        score += points

    score = min(100, score)
    medium_threshold = int(getattr(settings, "PROCTOR_MEDIUM_THRESHOLD", 20))
    high_threshold = int(getattr(settings, "PROCTOR_HIGH_THRESHOLD", 50))
    if score >= high_threshold:
        level = "ALTO"
    elif score >= medium_threshold:
        level = "MEDIO"
    else:
        level = "BAJO"
    return SuspicionAssessment(
        score=score,
        level=level,
        incident_count=sum(counts.values()),
        by_kind=counts,
    )
