from __future__ import annotations

import json

from services.speciesnet_api import app as speciesnet_app


class FakeSpeciesNetModel:
    def predict(self, **kwargs):
        filepaths = kwargs["filepaths"]
        assert len(filepaths) == 1
        return {
            "predictions": [
                {
                    "filepath": filepaths[0],
                    "classifications": {
                        "classes": [
                            "e1c6c5b2-b808-4d50-bf01-90aa46f964c2;mammalia;carnivora;felidae;panthera;tigris;tiger"
                        ],
                        "scores": [0.9991957545280457],
                    },
                    "detections": [
                        {
                            "category": "1",
                            "label": "animal",
                            "conf": 0.7193306684494019,
                            "bbox": [0.103515625, 0.0, 0.720703125, 0.998046875],
                        }
                    ],
                    "prediction": (
                        "e1c6c5b2-b808-4d50-bf01-90aa46f964c2;"
                        "mammalia;carnivora;felidae;panthera;tigris;tiger"
                    ),
                    "prediction_score": 0.9991957545280457,
                    "prediction_source": "classifier",
                    "model_version": "4.0.3a",
                }
            ]
        }


def test_speciesnet_cpu_service_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(speciesnet_app, "_model", FakeSpeciesNetModel())
    monkeypatch.setattr(speciesnet_app, "_model_error", None)
    monkeypatch.setattr(speciesnet_app, "CACHE_ENABLED", True)
    monkeypatch.setattr(speciesnet_app, "CACHE_DIR", tmp_path)

    payload = speciesnet_app.predict_image_bytes(
        b"fake-jpeg-bytes",
        filename="tiger.jpg",
        content_type="image/jpeg",
        top_k=3,
    )

    assert payload["ok"] is True
    assert payload["cached"] is False
    result = payload["result"]
    assert result["scientific_name"] == "Panthera tigris"
    assert result["score"] == 0.999196
    assert result["detections"][0]["label"] == "animal"
    assert result["detections"][0]["bbox"] == [0.103516, 0.0, 0.720703, 0.998047]
    assert "filepath" not in json.dumps(payload["raw"], ensure_ascii=False)

    cached = speciesnet_app.predict_image_bytes(
        b"fake-jpeg-bytes",
        filename="tiger.jpg",
        content_type="image/jpeg",
        top_k=3,
    )
    assert cached["cached"] is True
