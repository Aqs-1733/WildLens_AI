from __future__ import annotations

import mimetypes
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.database import get_db
from backend.deps import get_current_user
from backend.models import (
    ChatMessage,
    ChatThread,
    Comment,
    DiscoveryRecord,
    Friendship,
    Notification,
    ObservationLocation,
    ObservationPost,
    PostLike,
    Species,
    User,
    now_utc,
)
from backend.schemas import ChatMessageCreate, ChatThreadCreate, CommentCreate, FriendRequestCreate, PostCreate
from backend.services.text_clean import clean_text

router = APIRouter(prefix="/api/social", tags=["social"])
settings = get_settings()
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _user_brief(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": clean_text(user.display_name, f"用户{user.id}"),
        "avatar_url": user.avatar_url or "",
        "level": user.level,
        "stars": user.stars,
        "badges": _badges_for_user(user),
        "bio": clean_text(user.bio, "热爱自然，也热爱每一次发现。"),
    }


def _badges_for_user(user: User) -> list[str]:
    badges = ["探索者"]
    if user.level >= 5:
        badges.append("进阶观察者")
    if user.level >= 10:
        badges.append("自然导师")
    if user.stars >= 50:
        badges.append("星光收藏家")
    return badges


@router.post("/attachments")
async def upload_social_attachment(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> dict:
    content_type = (file.content_type or mimetypes.guess_type(file.filename or "")[0] or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WebP 图片")
    payload = await file.read(10 * 1024 * 1024 + 1)
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片不能超过 10MB")
    filename = f"post_{uuid.uuid4().hex}{ALLOWED_IMAGE_TYPES[content_type]}"
    path = settings.upload_dir / filename
    path.write_bytes(payload)
    return {"image_url": f"/media/uploads/{path.name}"}


def _notify(db: Session, user_id: int, actor_id: int | None, kind: str, title: str, body: str, payload: dict | None = None) -> None:
    db.add(
        Notification(
            user_id=user_id,
            actor_id=actor_id,
            kind=kind,
            title=title,
            body=body,
            payload=payload or {},
        )
    )


def _comment_dict(db: Session, comment: Comment) -> dict:
    author = db.get(User, comment.author_id)
    return {
        "id": comment.id,
        "content": comment.content,
        "created_at": comment.created_at,
        "author": _user_brief(author) if author else None,
    }


def _post_liked_by_user(db: Session, post_id: int, user_id: int) -> bool:
    return bool(
        db.scalar(
            select(PostLike.id).where(PostLike.post_id == post_id, PostLike.user_id == user_id)
        )
    )


@router.get("/friends")
def list_friends(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    friendships = db.scalars(
        select(Friendship).where(
            and_(
                Friendship.status == "accepted",
                or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id),
            )
        )
    ).all()
    friend_ids = [
        item.addressee_id if item.requester_id == user.id else item.requester_id
        for item in friendships
    ]
    friends = db.scalars(select(User).where(User.id.in_(friend_ids))).all() if friend_ids else []
    pending = db.scalars(
        select(Friendship).where(
            Friendship.addressee_id == user.id, Friendship.status == "pending"
        )
    ).all()
    pending_users = []
    for item in pending:
        requester = db.get(User, item.requester_id)
        if requester:
            pending_users.append({"friendship_id": item.id, "user": _user_brief(requester)})
    return {"friends": [_user_brief(item) for item in friends], "pending": pending_users}


@router.get("/users")
def search_users(
    q: str = "",
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    stmt = select(User).where(User.id != user.id)
    if q:
        stmt = stmt.where(or_(User.username.contains(q), User.display_name.contains(q)))
    return [_user_brief(item) for item in db.scalars(stmt.order_by(User.level.desc(), User.id).limit(limit)).all()]


@router.post("/friends/request")
def send_friend_request(
    payload: FriendRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    target = db.scalar(select(User).where(User.username == payload.username))
    if not target:
        raise HTTPException(status_code=404, detail="未找到该用户")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="不能添加自己")
    exists = db.scalar(
        select(Friendship).where(
            or_(
                and_(Friendship.requester_id == user.id, Friendship.addressee_id == target.id),
                and_(Friendship.requester_id == target.id, Friendship.addressee_id == user.id),
            )
        )
    )
    if exists:
        raise HTTPException(status_code=409, detail="好友关系或申请已存在")
    item = Friendship(requester_id=user.id, addressee_id=target.id, status="pending")
    db.add(item)
    db.flush()
    _notify(
        db,
        target.id,
        user.id,
        "friend_request",
        "新的好友申请",
        f"{user.display_name} 想和你成为观察好友。",
        {"friendship_id": item.id},
    )
    db.commit()
    return {"message": "好友申请已发送"}


@router.post("/friends/{friendship_id}/accept")
def accept_friend(
    friendship_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    item = db.get(Friendship, friendship_id)
    if not item or item.addressee_id != user.id:
        raise HTTPException(status_code=404, detail="好友申请不存在")
    item.status = "accepted"
    _notify(
        db,
        item.requester_id,
        user.id,
        "friend_accept",
        "好友申请已通过",
        f"{user.display_name} 已接受你的好友申请。",
        {"friendship_id": item.id},
    )
    db.commit()
    return {"message": "已成为好友"}


@router.delete("/friends/{friend_id}")
def remove_friend(
    friend_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    item = db.scalar(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(
                and_(Friendship.requester_id == user.id, Friendship.addressee_id == friend_id),
                and_(Friendship.requester_id == friend_id, Friendship.addressee_id == user.id),
            ),
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="好友关系不存在")
    db.delete(item)
    _notify(db, friend_id, user.id, "friend_remove", "好友关系已解除", f"{user.display_name} 已移除好友关系。")
    db.commit()
    return {"message": "好友已删除"}


@router.get("/feed")
def feed(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    friendships = db.scalars(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id),
        )
    ).all()
    friend_ids = {
        item.addressee_id if item.requester_id == user.id else item.requester_id
        for item in friendships
    }
    allowed_ids = friend_ids | {user.id}
    posts = db.scalars(
        select(ObservationPost)
        .where(
            or_(
                ObservationPost.visibility == "public",
                and_(ObservationPost.visibility == "friends", ObservationPost.author_id.in_(allowed_ids)),
                ObservationPost.author_id == user.id,
            )
        )
        .order_by(ObservationPost.created_at.desc())
        .limit(50)
    ).all()
    output = []
    for post in posts:
        author = db.get(User, post.author_id)
        comments = db.scalars(
            select(Comment)
            .where(Comment.post_id == post.id)
            .order_by(Comment.created_at.asc())
            .limit(5)
        ).all()
        comment_count = db.query(Comment).filter(Comment.post_id == post.id).count()
        output.append(
            {
                "id": post.id,
                "author": _user_brief(author) if author else None,
                "species": {
                    "id": post.species.id,
                    "common_name": post.species.common_name,
                    "scientific_name": post.species.scientific_name,
                    "category": post.species.category,
                    "color": post.species.color,
                }
                if post.species
                else None,
                "discovery": (
                    {
                        "id": record.id,
                        "record_type": record.record_type,
                        "title": record.title,
                        "scientific_name": record.scientific_name,
                        "category": record.category,
                        "image_url": record.image_url,
                        "confidence": record.confidence,
                        "behavior": record.behavior,
                        "phenomenon": record.phenomenon,
                    }
                    if post.discovery_id and (record := db.get(DiscoveryRecord, post.discovery_id))
                    else None
                ),
                "content": post.content,
                "image_url": post.image_url,
                "visibility": post.visibility,
                "likes": post.likes,
                "liked_by_me": _post_liked_by_user(db, post.id, user.id),
                "comment_count": comment_count,
                "comments": [_comment_dict(db, item) for item in comments],
                "created_at": post.created_at,
            }
        )
    return output


@router.get("/feed/recommendations")
def recommended_feed(
    refresh: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    observed = db.scalars(
        select(DiscoveryRecord).where(DiscoveryRecord.user_id == user.id).order_by(DiscoveryRecord.created_at.desc()).limit(100)
    ).all()
    observed_categories = {item.category for item in observed if item.category}
    observed_species = {item.scientific_name for item in observed if item.scientific_name}
    posts = db.scalars(
        select(ObservationPost)
        .where(ObservationPost.visibility == "public", ObservationPost.author_id != user.id)
        .order_by(ObservationPost.created_at.desc())
        .limit(200)
    ).all()
    ranked: list[tuple[int, ObservationPost]] = []
    for index, post in enumerate(posts):
        score = 0
        if post.species:
            if post.species.scientific_name in observed_species:
                score += 8
            if post.species.category in observed_categories:
                score += 4
            if post.species.scientific_name not in observed_species:
                score += 2
        score += max(0, 20 - index // 5)
        score += (refresh % 7) * (post.id % 3)
        ranked.append((score, post))
    selected = [post for _, post in sorted(ranked, key=lambda item: item[0], reverse=True)[:10]]
    return [_post_dict(db, post, user) for post in selected]


def _post_dict(db: Session, post: ObservationPost, user: User) -> dict:
    author = db.get(User, post.author_id)
    comment_count = db.query(Comment).filter(Comment.post_id == post.id).count()
    comments = db.scalars(
        select(Comment)
        .where(Comment.post_id == post.id)
        .order_by(Comment.created_at.asc())
        .limit(5)
    ).all()
    record = db.get(DiscoveryRecord, post.discovery_id) if post.discovery_id else None
    return {
        "id": post.id,
        "author": _user_brief(author) if author else None,
        "species": {
            "id": post.species.id,
            "common_name": post.species.common_name,
            "scientific_name": post.species.scientific_name,
            "category": post.species.category,
            "color": post.species.color,
        }
        if post.species
        else None,
        "discovery": (
            {
                "id": record.id,
                "record_type": record.record_type,
                "title": record.title,
                "scientific_name": record.scientific_name,
                "category": record.category,
                "image_url": record.image_url,
                "confidence": record.confidence,
                "behavior": record.behavior,
                "phenomenon": record.phenomenon,
            }
            if record
            else None
        ),
        "content": post.content,
        "image_url": post.image_url,
        "visibility": post.visibility,
        "likes": post.likes,
        "liked_by_me": _post_liked_by_user(db, post.id, user.id),
        "comment_count": comment_count,
        "comments": [_comment_dict(db, item) for item in comments],
        "created_at": post.created_at,
    }


@router.post("/posts")
def create_post(
    payload: PostCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if payload.species_id and not db.get(Species, payload.species_id):
        raise HTTPException(status_code=404, detail="物种不存在")
    if payload.discovery_id:
        discovery = db.get(DiscoveryRecord, payload.discovery_id)
        if not discovery or discovery.user_id != user.id:
            raise HTTPException(status_code=404, detail="识别记录不存在")
        if not payload.species_id and discovery.species_id:
            payload.species_id = discovery.species_id
        discovery.is_shared = True
    post = ObservationPost(author_id=user.id, **payload.model_dump())
    db.add(post)
    user.points += 10
    db.commit()
    db.refresh(post)
    return {"id": post.id, "message": "观察记录已发布"}


@router.post("/posts/{post_id}/like")
def like_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    post = db.get(ObservationPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="记录不存在")
    existing = db.scalar(select(PostLike).where(PostLike.post_id == post.id, PostLike.user_id == user.id))
    if existing:
        db.delete(existing)
        post.likes = max(0, int(post.likes or 0) - 1)
        liked = False
    else:
        db.add(PostLike(post_id=post.id, user_id=user.id))
        post.likes = int(post.likes or 0) + 1
        liked = True
    db.commit()
    return {"likes": post.likes, "liked": liked}


@router.get("/posts/{post_id}/comments")
def post_comments(
    post_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    post = db.get(ObservationPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="记录不存在")
    comments = db.scalars(
        select(Comment)
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
        .limit(100)
    ).all()
    return [_comment_dict(db, item) for item in comments]


@router.post("/posts/{post_id}/comments")
def create_comment(
    post_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    post = db.get(ObservationPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="记录不存在")
    comment = Comment(post_id=post_id, author_id=user.id, content=payload.content.strip())
    db.add(comment)
    if post.author_id != user.id:
        _notify(
            db,
            post.author_id,
            user.id,
            "post_comment",
            "新的动态评论",
            f"{user.display_name} 评论了你的观察动态。",
            {"post_id": post.id},
        )
    db.commit()
    db.refresh(comment)
    return _comment_dict(db, comment)


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    items = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(80)
    ).all()
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "title": item.title,
            "body": item.body,
            "payload": item.payload or {},
            "read": item.read,
            "created_at": item.created_at,
            "actor": _user_brief(actor) if item.actor_id and (actor := db.get(User, item.actor_id)) else None,
        }
        for item in items
    ]


@router.post("/notifications/{notification_id}/read")
def read_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    item = db.get(Notification, notification_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="提醒不存在")
    item.read = True
    db.commit()
    return {"message": "已读"}


def _thread_member_ids(thread: ChatThread) -> set[int]:
    return {int(item) for item in (thread.member_ids or [])}


def _thread_dict(db: Session, thread: ChatThread) -> dict:
    members = [db.get(User, item) for item in _thread_member_ids(thread)]
    last = db.scalar(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    return {
        "id": thread.id,
        "title": thread.title,
        "thread_type": thread.thread_type,
        "members": [_user_brief(item) for item in members if item],
        "last_message": last.content if last else "",
        "updated_at": thread.updated_at,
        "created_at": thread.created_at,
    }


@router.get("/chats")
def list_chats(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    threads = db.scalars(select(ChatThread).order_by(ChatThread.updated_at.desc())).all()
    return [_thread_dict(db, item) for item in threads if user.id in _thread_member_ids(item)]


@router.post("/chats")
def create_chat(
    payload: ChatThreadCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    member_ids = {user.id, *[int(item) for item in payload.member_ids if int(item) != user.id]}
    if len(member_ids) < 2:
        raise HTTPException(status_code=400, detail="至少选择一位成员")
    for member_id in member_ids:
        if not db.get(User, member_id):
            raise HTTPException(status_code=404, detail=f"用户 {member_id} 不存在")
    title = payload.title.strip()
    if not title:
        names = [db.get(User, item).display_name for item in member_ids if db.get(User, item)]
        title = "、".join(names[:4])
    thread = ChatThread(
        title=title[:180],
        thread_type="group" if len(member_ids) > 2 else "direct",
        owner_id=user.id,
        member_ids=sorted(member_ids),
        updated_at=now_utc(),
    )
    db.add(thread)
    db.flush()
    for member_id in member_ids:
        if member_id != user.id:
            _notify(db, member_id, user.id, "chat_invite", "新的聊天", f"{user.display_name} 邀请你加入“{thread.title}”。", {"thread_id": thread.id})
    db.commit()
    return _thread_dict(db, thread)


@router.get("/chats/{thread_id}/messages")
def chat_messages(
    thread_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    thread = db.get(ChatThread, thread_id)
    if not thread or user.id not in _thread_member_ids(thread):
        raise HTTPException(status_code=404, detail="聊天不存在")
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread.id)
        .order_by(ChatMessage.created_at)
        .limit(300)
    ).all()
    return [
        {
            "id": item.id,
            "sender": _user_brief(sender) if (sender := db.get(User, item.sender_id)) else None,
            "content": item.content,
            "image_url": item.image_url,
            "created_at": item.created_at,
        }
        for item in messages
    ]


@router.post("/chats/{thread_id}/messages")
def send_chat_message(
    thread_id: int,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    thread = db.get(ChatThread, thread_id)
    if not thread or user.id not in _thread_member_ids(thread):
        raise HTTPException(status_code=404, detail="聊天不存在")
    if not payload.content.strip() and not payload.image_url.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    message = ChatMessage(
        thread_id=thread.id,
        sender_id=user.id,
        content=payload.content.strip(),
        image_url=payload.image_url.strip(),
    )
    thread.updated_at = now_utc()
    db.add(message)
    for member_id in _thread_member_ids(thread):
        if member_id != user.id:
            _notify(db, member_id, user.id, "chat_message", f"{thread.title} 有新消息", payload.content[:80], {"thread_id": thread.id})
    db.commit()
    return {"message": "已发送", "id": message.id}
