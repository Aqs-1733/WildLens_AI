# Training Advisor Skill

## Purpose
Analyze model metrics and review corrections to recommend the next training data acquisition step.

## Checks
Class imbalance, camera-location leakage, nighttime/infrared coverage, rare-class recall, calibration, confusion pairs, corrupt files, duplicates and license completeness.

## Output
A ranked list of data gaps with proposed source, sample count, annotation type and acceptance metric. Never claim that a model has been trained when weights are absent.
