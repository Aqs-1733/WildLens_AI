from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _project_path(value: Path) -> Path:
    return value if value.is_absolute() else PROJECT_ROOT / value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "识境"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8010
    frontend_url: str = "http://127.0.0.1:5174"
    secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 10080
    regulator_invite_code: str = "WILD-REG-2026"
    database_url: str = ""
    wildlens_db_path: Path = Field(default=PROJECT_ROOT / "storage" / "wildlens.db")
    species_queue_db_path: Path = Field(default=PROJECT_ROOT / "storage" / "species_image_bank.sqlite")
    species_embedding_db_path: Path = Field(default=PROJECT_ROOT / "storage" / "species_visual_embeddings.sqlite")
    global_species_index_path: Path = Field(default=PROJECT_ROOT / "models" / "metadata" / "global_species_index")
    species_image_root: Path = Field(default=Path("/root/autodl-tmp/datasets/wildlens_species_bank/curated/inaturalist"))
    inat_dwca_path: Path = Field(default=Path("/root/autodl-tmp/datasets/inaturalist_dwca/gbif-observations-dwca.zip"))
    catalogue_of_life_path: Path = Field(default=PROJECT_ROOT / "data" / "raw" / "catalogue_of_life_2026-06-19_XR_ColDP.zip")
    model_registry_dir: Path = Field(default=PROJECT_ROOT / "models" / "registry")
    model_checkpoint_dir: Path = Field(default=PROJECT_ROOT / "models" / "checkpoints")
    active_model_config: Path = Field(default=PROJECT_ROOT / "models" / "registry" / "active_model.json")
    output_media_dir: Path = Field(default=PROJECT_ROOT / "storage" / "outputs")
    logs_dir: Path = Field(default=PROJECT_ROOT / "storage" / "logs")
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174,capacitor://localhost,http://localhost"

    ark_api_key: str = ""
    ark_openai_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_dns_fallback_ip: str = ""
    ark_model: str = "doubao-seed-evolving"
    ark_image_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_image_model: str = "doubao-seed-evolving"
    ai_correction_enabled: bool = True
    ai_correction_min_confidence: float = 0.62
    ai_correction_statuses: str = "unknown,fallback,review"
    video_ai_max_calls: int = 3

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "Shijing-AI"
    langsmith_api_key: str = ""

    max_upload_mb: int = 1024
    max_photo_mb: int = 20
    video_sample_fps: float = 2.0
    ffmpeg_path: str = Field(default="ffmpeg", validation_alias=AliasChoices("FFMPEG_PATH", "FFMPEG_BINARY"))
    ffprobe_path: str = Field(default="ffprobe", validation_alias=AliasChoices("FFPROBE_PATH", "FFPROBE_BINARY"))
    ffmpeg_preset: str = "veryfast"
    ffmpeg_crf: int = 23
    ffmpeg_timeout_seconds: int = 1800
    vision_mode: str = "hybrid"
    yolo_model_path: str = "./models/trained/wildlens_yolo26s_mammal_bird_v5.onnx"
    custom_wildlife_model_path: str = "./models/onnx/wildlife_species.onnx"
    fire_smoke_model_path: str = "./models/onnx/fire_smoke.onnx"
    behavior_model_path: str = "./models/onnx/animal_behavior.onnx"
    phenomena_model_path: str = "./models/onnx/natural_phenomena.onnx"
    detection_confidence: float = 0.35
    plant_min_area_ratio: float = 0.035
    redis_url: str = "redis://localhost:6379/0"

    speciesnet_enabled: bool = True
    speciesnet_api_url: str = "http://127.0.0.1:8101"
    speciesnet_timeout_seconds: float = 120.0
    speciesnet_connect_timeout_seconds: float = 5.0
    speciesnet_read_timeout_seconds: float = 120.0
    speciesnet_write_timeout_seconds: float = 30.0
    speciesnet_pool_timeout_seconds: float = 5.0
    speciesnet_min_score: float = 0.65
    speciesnet_strong_score: float = 0.90
    speciesnet_cache_enabled: bool = True
    speciesnet_model_name: str = "kaggle:google/speciesnet/pyTorch/v4.0.3a/1"
    speciesnet_model_version: str = "4.0.3a"
    speciesnet_api_python: Path = Field(
        default=PROJECT_ROOT / ".venv-speciesnet-cpu" / "Scripts" / "python.exe"
    )
    speciesnet_api_host: str = "127.0.0.1"
    speciesnet_api_port: int = 8101
    speciesnet_max_image_mb: int = 25
    speciesnet_cache_dir: Path = Field(default=PROJECT_ROOT / "storage" / "speciesnet_cache")

    bioclip_enabled: bool = True
    bioclip_model_id: str = "hf-hub:imageomics/bioclip"
    bioclip_embedding_dim: int = 512
    bioclip_hf_home: Path = Field(
        default=PROJECT_ROOT
        / "storage"
        / "cloud_migration"
        / "wildlens_compact_prototype_pack"
        / "models"
        / "hf_cache"
    )
    bioclip_prototype_db_path: Path = Field(
        default=PROJECT_ROOT
        / "storage"
        / "cloud_migration"
        / "wildlens_compact_prototype_pack"
        / "storage"
        / "species_prototypes_inference.sqlite"
    )
    bioclip_device: str = "cpu"
    bioclip_top_k: int = 10
    bioclip_batch_size: int = 16384
    bioclip_search_backend: str = "memory"
    bioclip_index_dtype: str = "float16"
    bioclip_preload_index: bool = True
    bioclip_preload_model: bool = True
    bioclip_query_cache_size: int = 128
    bioclip_full_image_fallback: bool = True
    bioclip_full_image_fallback_weak_only: bool = True
    bioclip_min_similarity: float = 0.55
    bioclip_strong_similarity: float = 0.78
    bioclip_min_margin: float = 0.01

    active_learning_enabled: bool = True
    active_learning_runtime_enabled: bool = True
    active_learning_embedding_db_path: Path = Field(
        default=PROJECT_ROOT / "storage" / "active_learning" / "streamed_embeddings.sqlite"
    )
    active_learning_min_similarity: float = 0.86
    active_learning_supported_min_similarity: float = 0.80
    active_learning_min_margin: float = 0.04
    active_learning_min_support: int = 2
    active_learning_accept_min_confidence: float = 0.78

    upload_dir: Path = Field(default=PROJECT_ROOT / "storage" / "uploads")
    result_dir: Path = Field(default=PROJECT_ROOT / "storage" / "results")
    annotated_dir: Path = Field(default=PROJECT_ROOT / "storage" / "annotated")
    playback_dir: Path = Field(default=PROJECT_ROOT / "storage" / "playback")
    report_dir: Path = Field(default=PROJECT_ROOT / "storage" / "reports", validation_alias=AliasChoices("REPORT_DIR", "REPORT_OUTPUT_DIR"))
    sample_video_dir: Path = Field(default=PROJECT_ROOT / "data" / "sample_videos", validation_alias=AliasChoices("SAMPLE_VIDEO_DIR", "SAMPLE_MEDIA_DIR"))

    @property
    def cors_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def is_test(self) -> bool:
        return self.app_env.lower() == "test"

    @property
    def ai_correction_status_set(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.ai_correction_statuses.split(",")
            if item.strip()
        }

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{_project_path(self.wildlens_db_path).as_posix()}"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for attr in (
        "wildlens_db_path",
        "species_queue_db_path",
        "species_embedding_db_path",
        "global_species_index_path",
        "catalogue_of_life_path",
        "model_registry_dir",
        "model_checkpoint_dir",
        "active_model_config",
        "output_media_dir",
        "upload_dir",
        "result_dir",
        "annotated_dir",
        "playback_dir",
        "report_dir",
        "sample_video_dir",
        "logs_dir",
        "speciesnet_api_python",
        "speciesnet_cache_dir",
        "bioclip_hf_home",
        "bioclip_prototype_db_path",
        "active_learning_embedding_db_path",
    ):
        value = getattr(settings, attr)
        setattr(settings, attr, _project_path(value))
    for directory in (
        settings.wildlens_db_path.parent,
        settings.species_queue_db_path.parent,
        settings.species_embedding_db_path.parent,
        settings.model_registry_dir,
        settings.model_checkpoint_dir,
        settings.output_media_dir,
        settings.upload_dir,
        settings.result_dir,
        settings.annotated_dir,
        settings.playback_dir,
        settings.report_dir,
        settings.sample_video_dir,
        settings.logs_dir,
        settings.speciesnet_cache_dir,
        settings.active_learning_embedding_db_path.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    if not settings.active_model_config.exists():
        settings.active_model_config.write_text(
            '{\n'
            '  "active_species_model": null,\n'
            f'  "prototype_database": "{settings.species_embedding_db_path.as_posix()}",\n'
            f'  "global_species_index": "{settings.global_species_index_path.as_posix()}",\n'
            '  "fallback_model": "hf-hub:imageomics/bioclip",\n'
            '  "updated_at": null\n'
            '}\n',
            encoding="utf-8",
        )
    return settings
