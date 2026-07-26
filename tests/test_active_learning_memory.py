from __future__ import annotations

import numpy as np

from backend.vision.active_learning_memory import ActiveLearningMemory


def test_active_learning_memory_accepts_clear_trusted_vector(tmp_path):
    memory = ActiveLearningMemory(tmp_path / "memory.sqlite")
    query = np.ones(512, dtype=np.float32)
    opposite = -query

    memory.store_labeled_vector(
        query,
        scientific_name="Elephas maximus",
        common_name="Asian elephant",
        category="mammal",
        label_source="human-review",
        label_confidence=1.0,
        accepted_for_runtime=True,
    )
    memory.store_labeled_vector(
        query + np.eye(1, 512, 0, dtype=np.float32)[0] * 0.01,
        scientific_name="Elephas maximus",
        common_name="Asian elephant",
        category="mammal",
        label_source="human-review",
        label_confidence=1.0,
        accepted_for_runtime=True,
    )
    memory.store_labeled_vector(
        opposite,
        scientific_name="Loxodonta africana",
        common_name="African elephant",
        category="mammal",
        label_source="human-review",
        label_confidence=1.0,
        accepted_for_runtime=True,
    )

    result = memory.query(query)

    assert result
    assert result["scientific_name"] == "Elephas maximus"
    assert result["active_learning_accepted"] is True
    assert result["active_learning_support"] == 2


def test_active_learning_memory_rejects_zero_margin_conflict(tmp_path):
    memory = ActiveLearningMemory(tmp_path / "memory.sqlite")
    query = np.ones(512, dtype=np.float32)

    memory.store_labeled_vector(
        query,
        scientific_name="Panthera pardus",
        common_name="Leopard",
        category="mammal",
        label_source="gbif-stream",
        label_confidence=0.9,
        accepted_for_runtime=True,
    )
    memory.store_labeled_vector(
        query,
        scientific_name="Panthera onca",
        common_name="Jaguar",
        category="mammal",
        label_source="gbif-stream",
        label_confidence=0.9,
        accepted_for_runtime=True,
    )

    result = memory.query(query)

    assert result
    assert result["active_learning_margin"] == 0.0
    assert result["active_learning_accepted"] is False
