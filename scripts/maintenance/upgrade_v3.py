from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import delete, func, select

from backend.core.config import get_settings
from backend.core.database import Base, SessionLocal, engine
from backend.models import (
    AnalysisJob,
    Detection,
    DiscoveryRecord,
    MediaFile,
    MediaVariant,
    TrackKeyframe,
    UserCollection,
    VideoTrack,
)
from backend.services.video_transcode import (
    VideoTranscodeError,
    probe_video,
    transcode_browser_video,
    transcode_silent_video,
)

settings = get_settings()


def rebuild_collections() -> dict:
    with SessionLocal() as db:
        favorites = {
            (row.user_id, row.species_id): row.favorite
            for row in db.scalars(select(UserCollection)).all()
        }
        db.execute(delete(UserCollection))
        rows = db.execute(
            select(
                DiscoveryRecord.user_id,
                DiscoveryRecord.species_id,
                func.count(DiscoveryRecord.id),
                func.min(DiscoveryRecord.created_at),
                func.max(DiscoveryRecord.created_at),
                func.max(DiscoveryRecord.stars_earned),
            )
            .where(DiscoveryRecord.species_id.is_not(None))
            .group_by(DiscoveryRecord.user_id, DiscoveryRecord.species_id)
        ).all()
        for user_id, species_id, count, first_at, last_at, stars in rows:
            db.add(
                UserCollection(
                    user_id=user_id,
                    species_id=species_id,
                    discovered_count=count,
                    knowledge_progress=0,
                    stars_earned=max(1, int(stars or 1)),
                    favorite=favorites.get((user_id, species_id), False),
                    first_discovered_at=first_at,
                    last_discovered_at=last_at,
                )
            )
        db.commit()
        return {"collections_rebuilt": len(rows)}


def create_legacy_tracks() -> dict:
    created_tracks = created_keyframes = 0
    with SessionLocal() as db:
        jobs = db.scalars(select(AnalysisJob)).all()
        for job in jobs:
            if db.scalar(select(func.count(VideoTrack.id)).where(VideoTrack.job_id == job.id)):
                continue
            detections = db.scalars(
                select(Detection)
                .where(Detection.job_id == job.id)
                .order_by(Detection.track_id, Detection.timestamp_ms)
            ).all()
            grouped: dict[int, list[Detection]] = defaultdict(list)
            for item in detections:
                grouped[item.track_id].append(item)
            for track_id, items in grouped.items():
                if not items:
                    continue
                best = max(items, key=lambda row: row.confidence)
                track = VideoTrack(
                    job_id=job.id,
                    track_id=track_id,
                    species_id=best.species_id,
                    category=best.category,
                    label=best.label,
                    scientific_name=best.scientific_name,
                    confidence=max(row.confidence for row in items),
                    color=best.color,
                    start_ms=min(row.timestamp_ms for row in items),
                    end_ms=max(row.timestamp_ms for row in items),
                    source="legacy-migration",
                    alternatives=best.alternatives or [],
                )
                db.add(track)
                db.flush()
                created_tracks += 1
                for item in items:
                    db.add(
                        TrackKeyframe(
                            video_track_id=track.id,
                            timestamp_ms=item.timestamp_ms,
                            bbox=item.bbox or {},
                            confidence=item.confidence,
                        )
                    )
                    created_keyframes += 1
        db.commit()
    return {"tracks_created": created_tracks, "keyframes_created": created_keyframes}


def transcode_existing(force: bool = False) -> dict:
    converted = skipped = failed = 0
    errors: list[str] = []
    with SessionLocal() as db:
        media_rows = db.scalars(select(MediaFile).where(MediaFile.media_type == "video")).all()
        for media in media_rows:
            source = Path(media.stored_path)
            if not source.exists():
                failed += 1
                errors.append(f"media {media.id}: source missing {source}")
                continue
            variant = db.scalar(
                select(MediaVariant).where(
                    MediaVariant.media_id == media.id,
                    MediaVariant.kind == "playback",
                )
            )
            if variant and Path(variant.stored_path).exists() and not force:
                try:
                    if probe_video(Path(variant.stored_path)).video_codec == "h264":
                        skipped += 1
                        continue
                except VideoTranscodeError as exc:
                    errors.append(f"media {media.id}: existing playback probe failed, regenerating: {exc}")
            destination = settings.playback_dir / f"media_{media.id}_playback.mp4"
            try:
                probe = transcode_browser_video(source, destination)
            except VideoTranscodeError as exc:
                failed += 1
                errors.append(f"media {media.id}: {exc}")
                continue
            if variant:
                variant.stored_path = str(destination)
                variant.codec = "h264"
                variant.mime_type = "video/mp4"
            else:
                db.add(
                    MediaVariant(
                        media_id=media.id,
                        kind="playback",
                        stored_path=str(destination),
                        codec="h264",
                        mime_type="video/mp4",
                    )
                )
            media.duration_seconds = probe.duration_seconds
            converted += 1

        annotated_rows = db.scalars(
            select(MediaVariant).where(MediaVariant.kind == "annotated")
        ).all()
        for variant in annotated_rows:
            source = Path(variant.stored_path)
            if not source.exists():
                continue
            try:
                if probe_video(source).video_codec == "h264" and not force:
                    continue
                destination = source.with_name(f"{source.stem}_h264.mp4")
                transcode_silent_video(source, destination)
                variant.stored_path = str(destination)
                variant.codec = "h264"
            except VideoTranscodeError as exc:
                errors.append(f"annotated {variant.id}: {exc}")
        db.commit()
    return {"videos_converted": converted, "videos_skipped": skipped, "videos_failed": failed, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="Upgrade an existing 识境 database and media library")
    parser.add_argument("--transcode-all", action="store_true")
    parser.add_argument("--force-transcode", action="store_true")
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    report = {"schema": "created-or-current"}
    report.update(rebuild_collections())
    report.update(create_legacy_tracks())
    if args.transcode_all:
        report.update(transcode_existing(args.force_transcode))
    output = settings.result_dir.parent / "logs" / "upgrade_v3.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"升级报告：{output}")
    return 0 if not report.get("videos_failed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
