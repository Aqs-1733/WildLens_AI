# Risk Triage Skill

## Purpose
Prioritize environmental monitoring events for regulators without turning a visual detection into a legal conclusion.

## Inputs
Detection/track summaries, zone settings, event time, duration, confidence, prior events and review status.

## Rules
- Person or vehicle detection means “疑似闯入”, never “偷猎者”.
- Fire/smoke requires temporal or multi-frame confirmation before high severity.
- Low-confidence or conflicting predictions must enter manual review.
- A rare species near a road may raise ecological risk, but does not imply injury.
- Recommendations must be reversible, proportionate and auditable.

## Output
Severity, evidence list, uncertainty, recommended next action, and whether human review is mandatory.
