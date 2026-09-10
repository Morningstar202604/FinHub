"""Self-verification auditor (ROADMAP M2-D) — code-level, LLM-free.

An offline, deterministic auditor that scans an investment research text for
the three most common credibility failures before it ships:

    1. **Number verification** — dollar/percent figures are cross-checked
       against known data points (e.g. pulled quotes, financial statements).
       A delta beyond a configurable tolerance is flagged as a possible
       mistatement.
    2. **Citation gating** — key factual claims (financial metrics, ratings,
       catalysts) are expected to have a provenance record; claims without one
       are listed so the pipeline can demand evidence.
    3. **Internal conflict** — the same metric/symbol appearing with two
       materially different values in one text is flagged (e.g. "margin 45%"
       vs "margin 55%").

No external calls, no LLM: pure functions over strings and small dicts, so
the auditor is unit-testable and safe to run inside any stage of the research
loop (idea/data/model/report).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Number extraction — USD / other-currency amounts, percentages, multipliers.
# ---------------------------------------------------------------------------

# $1.23B, $12.5M, 1,200, 1.2 亿, 45%, ×2.3 / 2.3x
_USD_RE = re.compile(
    r"\$\s*([0-9][0-9,\.]*)\s*(B|M|K|千|亿|万|million|billion|m|b)?\b",
    re.IGNORECASE,
)
_PCT_RE = re.compile(r"([0-9][0-9,\.]*)\s*(%|％)")
_MULT_RE = re.compile(r"([0-9][0-9,\.]*)\s*[xX×]")
_CN_NUM_RE = re.compile(r"([0-9][0-9,\.]*)\s*(亿|千万|万)")

# Canonical suffixes we normalize to USD millions (approximate, for deltas).
_SUFFIX_FACTOR: dict[str, float] = {
    "k": 0.001,
    "K": 0.001,
    "m": 1.0,
    "M": 1.0,
    "b": 1000.0,
    "B": 1000.0,
    "亿": 1000.0 * 6.9,  # ~ CNY 1亿 ≈ USD 6.9M (display estimate; deltas only)
    "千万": 1000.0 * 0.69,
    "万": 0.69,
}


@dataclass(frozen=True)
class ExtractedNumber:
    """One number found in the text, with its normalized USD-millions value (or None)."""

    raw: str
    value_usd_m: float | None
    kind: str  # "usd" | "pct" | "mult" | "cn_tare"


@dataclass(frozen=True)
class AuditFinding:
    """One credibility finding. Level: info | warning | error."""

    level: str
    kind: str  # "noverify" | "uncited" | "conflict"
    message: str
    evidence: str = ""
    threshold_delta: float | None = None


@dataclass(frozen=True)
class AuditReport:
    report_text: str
    findings: tuple[AuditFinding, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        """No error-level findings — report is cleared to advance."""
        return not any(f.level == "error" for f in self.findings)

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.level == "warning")

    def errors(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.level == "error"]


def extract_numbers(text: str) -> list[ExtractedNumber]:
    """Collect every money/percent/multiplier token in the text."""
    found: list[ExtractedNumber] = []
    for m in _USD_RE.finditer(text):
        found.append(
            ExtractedNumber(
                raw=m.group(0),
                value_usd_m=_scale(m.group(1), m.group(2) or ""),
                kind="usd",
            )
        )
    for m in _PCT_RE.finditer(text):
        found.append(
            ExtractedNumber(raw=m.group(0), value_usd_m=None, kind="pct")
        )
    for m in _MULT_RE.finditer(text):
        found.append(
            ExtractedNumber(raw=m.group(0), value_usd_m=None, kind="mult")
        )
    for m in _CN_NUM_RE.finditer(text):
        found.append(
            ExtractedNumber(
                raw=m.group(0),
                value_usd_m=_scale(m.group(1), m.group(2)),
                kind="cn_tare",
            )
        )
    return found


def _scale(number_str: str, suffix: str) -> float | None:
    """Normalize a '$1.23' + suffix to USD millions; None when unparseable."""
    cleaned = number_str.replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    factor = _SUFFIX_FACTOR.get(suffix, 1.0)
    return value * factor if suffix else value * 1e-6  # bare USD -> millions


# ---------------------------------------------------------------------------
# The auditor itself.
# ---------------------------------------------------------------------------

# Terms that make a sentence a *verifiable factual claim* rather than opinion.
_CLAIM_MARKERS = (
    "营收",
    "收入",
    "利润",
    "净利",
    "净利润",
    "毛利率",
    "净利率",
    "毛利率",
    "ebitda",
    "eps",
    "市值",
    "估值",
    "目标价",
    "评级",
    "pe",
    "peg",
    "增长",
    "同比",
    "环比",
    "增长率",
    "负债",
    "现金",
    "现金流",
    "订单",
    "出货",
    "销量",
    "库存",
    "毛利率",
)


def audit_report(
    text: str,
    *,
    known_data: dict[str, float] | None = None,
    provenance_sources: Iterable[str] = (),
    num_tolerance_pct: float = 2.0,
) -> AuditReport:
    """Run all three checks over ``text``.

    Args:
        text: the report/memo body under review.
        known_data: metric->USD-millions (or scalar) baseline to verify against.
        provenance_sources: source ids already recorded for this work
            (e.g. SEC filing ids, provider keys, URLs). Claims that reference
            none of them get a warning.
        num_tolerance_pct: max accepted relative delta for number cross-checks.
    """
    findings: list[AuditFinding] = []
    lowered = text.lower()

    # 1. Number verification against known data points.
    if known_data:
        for metric, expected in known_data.items():
            # Find occurrences of the metric followed by a dollar figure.
            pat = re.compile(
                re.escape(metric) + r"[^\n$]{0,24}\$?\s*([0-9][0-9,\.]*)\s*(B|M|b|m|亿|万)?",
                re.IGNORECASE,
            )
            matched = False
            for m in pat.finditer(text):
                raw_val = m.group(1).replace(",", "")
                try:
                    found_val = float(raw_val) * _SUFFIX_FACTOR.get(m.group(2) or "M", 1.0)
                except ValueError:
                    continue
                matched = True
                if expected:
                    delta = abs(found_val - expected) / abs(expected) * 100.0
                    if delta > num_tolerance_pct:
                        findings.append(
                            AuditFinding(
                                level="error",
                                kind="noverify",
                                message=(
                                    f"数字与基准不符: {metric} 文本值 ¥{raw_val}{m.group(2) or 'M'} "
                                    f"vs 基准 {expected} (偏差 {delta:.1f}%，阈值 {num_tolerance_pct}%)"
                                ),
                                evidence=metric,
                                threshold_delta=delta,
                            )
                        )
            if not matched:
                findings.append(
                    AuditFinding(
                        level="warning",
                        kind="noverify",
                        message=f"关键指标 {metric} 无可交叉验证数字",
                        evidence=metric,
                    )
                )

    # 2. Citation gating — factual claims should touch a provenance source.
    if provenance_sources:
        src_set = {s.lower() for s in provenance_sources}
        has_numbers = bool(extract_numbers(text))
        for marker in _CLAIM_MARKERS:
            for m in re.finditer(re.escape(marker), lowered):
                window = lowered[max(0, m.start() - 40): m.start() + 60]
                if not any(s in window for s in src_set):
                    # A concrete number with no source is a hard miss (the
                    # number is a falsifiable claim); a bare keyword without
                    # figures is a soft gap. Distinguish so the evals suite
                    # can gate on the hard case.
                    level = "error" if has_numbers else "warning"
                    findings.append(
                        AuditFinding(
                            level=level,
                            kind="uncited",
                            message=f"关键论断「{marker}」附近未发现对应数据来源",
                            evidence=window[:90].strip(),
                        )
                    )
                    break  # one flag per metric, avoid noise

    # 3. Internal conflict — same metric, two materially different values.
    conflict_pairs = _find_metric_conflicts(text)
    for metric, values in conflict_pairs:
        findings.append(
            AuditFinding(
                level="error",
                kind="conflict",
                message=f"文字内 {metric} 出现矛盾数值: {', '.join(values)}",
                evidence=metric,
            )
        )

    return AuditReport(report_text=text, findings=tuple(findings))


_CONFLICT_METRIC_RE = re.compile(
    r"((?:毛利率|净利率|增速|增长率|目标价|eps|pe|peg|市值|营收|收入|净利润))\s*[^\n]{0,12}?\s*([0-9][0-9,\.]*)\s*(%|％|x)?",
)


def _find_metric_conflicts(text: str) -> list[tuple[str, set[str]]]:
    """Return metrics that appear with two or more distinct numeric values."""
    buckets: dict[str, set[str]] = {}
    for m in _CONFLICT_METRIC_RE.finditer(text):
        metric = m.group(1).strip()
        value = f"{m.group(2)}{m.group(3) or ''}"
        buckets.setdefault(metric, set()).add(value)
    return [(metric, values) for metric, values in buckets.items() if len(values) > 1]


if __name__ == "__main__":  # quick self-check: python -m src.tools.research_qa.auditor
    demo = (
        "FY2025 营收为 $12.4B，毛利率 45%。目标价评级提高至买入。"
        "注意：文中毛利率同时写为 55%，存在不一致。"
    )
    report = audit_report(demo, known_data={"营收": 18_000.0})
    for f in report.findings:
        print(f"[{f.level}] {f.message}")