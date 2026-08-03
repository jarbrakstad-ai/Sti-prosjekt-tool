"""Pydantic-modeller brukt av API-et (kun for dokumentasjon/validering av respons)."""
from __future__ import annotations

from pydantic import BaseModel


class Summary(BaseModel):
    total_length_m: float
    elevation_gain_m: float
    elevation_loss_m: float
    avg_grade_pct: float
    max_grade_pct: float
    num_segments: int
    flagged_segments: int
    flag_counts: dict[str, int]
    sustainability_score: float


class Segment(BaseModel):
    index: int
    start: tuple[float, float]
    end: tuple[float, float]
    length_m: float
    grade_pct: float
    cross_slope_pct: float | None
    half_rule_ratio: float | None
    fall_line_angle_deg: float | None
    flags: list[str]


class AnalyzeResponse(BaseModel):
    summary: Summary
    recommendations: list[str]
    segments: list[Segment]
