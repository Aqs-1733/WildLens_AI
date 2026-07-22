# Species QA Skill

## Purpose
Answer a question about the currently selected animal or plant while separating video observations, model inference, and general knowledge.

## Required context
- Species card: common name, scientific name, taxonomy, habitat, traits, protection level.
- Current detection: timestamp, confidence, track id, bounding box and behavior result.
- Retrieved knowledge passages with source identifiers.
- Optional analysis-job summary and nearby risk events.

## Procedure
1. Resolve aliases and verify scientific name against the taxonomy table.
2. State observable facts from the selected video first.
3. Mark uncertain model results with words such as “疑似”“模型推测”.
4. Use retrieved knowledge only when it supports the answer.
5. Never invent population counts, legal protection level, location or behavior.
6. Give one useful follow-up question.

## Output
A short Chinese answer with sections: 观察事实、可能解释、科普知识、需要确认。Return source ids separately.
