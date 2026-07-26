import { useEffect, useMemo, useState } from 'react'
import { Bell, CheckCircle2, Heart, ImagePlus, MessageCircle, RefreshCw, Search, Send, Trash2, UserPlus, Users, X } from 'lucide-react'
import { api, mediaUrl } from '../api/client'
import type { Species } from '../types'

interface Friend { id: number; username: string; display_name: string; avatar_url: string; level: number; stars: number; badges: string[]; bio: string }
interface PendingFriend { friendship_id: number; user: Friend }
interface FeedComment { id: number; author: Friend | null; content: string; created_at: string }
interface FeedPost { id: number; author: Friend | null; species: { id: number; common_name: string; scientific_name: string; color: string } | null; discovery?: { title: string; image_url: string } | null; content: string; image_url: string; visibility: string; likes: number; liked_by_me: boolean; comment_count: number; comments?: FeedComment[]; created_at: string }
interface Notice { id: number; title: string; body: string; read: boolean; created_at: string; actor?: Friend | null; payload: Record<string, unknown> }
interface ChatThread { id: number; title: string; thread_type: string; members: Friend[]; last_message: string; updated_at: string }
interface ChatMessage { id: number; sender: Friend | null; content: string; image_url: string; created_at: string }

function Avatar({ user }: { user?: Friend | null }) {
  if (user?.avatar_url) return <img className="avatar-circle avatar-image" src={user.avatar_url} alt={user.display_name} />
  return <div className="avatar-circle">{(user?.display_name || '识').slice(0, 1)}</div>
}

export default function CommunityPage() {
  const [friends, setFriends] = useState<Friend[]>([])
  const [pending, setPending] = useState<PendingFriend[]>([])
  const [feed, setFeed] = useState<FeedPost[]>([])
  const [recommended, setRecommended] = useState<FeedPost[]>([])
  const [notices, setNotices] = useState<Notice[]>([])
  const [users, setUsers] = useState<Friend[]>([])
  const [species, setSpecies] = useState<Species[]>([])
  const [username, setUsername] = useState('')
  const [userQuery, setUserQuery] = useState('')
  const [postQuery, setPostQuery] = useState('')
  const [content, setContent] = useState('')
  const [speciesId, setSpeciesId] = useState('')
  const [visibility, setVisibility] = useState('public')
  const [postImageUrl, setPostImageUrl] = useState('')
  const [uploadingPostImage, setUploadingPostImage] = useState(false)
  const [refreshSeed, setRefreshSeed] = useState(0)
  const [threads, setThreads] = useState<ChatThread[]>([])
  const [selectedThread, setSelectedThread] = useState<ChatThread | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [chatText, setChatText] = useState('')
  const [groupTitle, setGroupTitle] = useState('')
  const [groupMembers, setGroupMembers] = useState<string[]>([])

  const load = () => Promise.all([
    api<{ friends: Friend[]; pending: PendingFriend[] }>('/api/social/friends'),
    api<FeedPost[]>('/api/social/feed'),
    api<FeedPost[]>(`/api/social/feed/recommendations?refresh=${refreshSeed}`),
    api<Notice[]>('/api/social/notifications'),
    api<Species[]>('/api/species?mine=true'),
    api<ChatThread[]>('/api/social/chats'),
  ]).then(([friendData, posts, recs, noticeRows, speciesRows, chatRows]) => {
    setFriends(friendData.friends); setPending(friendData.pending); setFeed(posts); setRecommended(recs); setNotices(noticeRows); setSpecies(speciesRows); setThreads(chatRows)
  })
  useEffect(() => { void load() }, [refreshSeed])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (userQuery.trim()) void api<Friend[]>(`/api/social/users?q=${encodeURIComponent(userQuery.trim())}`).then(setUsers)
      else setUsers([])
    }, 250)
    return () => window.clearTimeout(timer)
  }, [userQuery])

  useEffect(() => {
    if (!selectedThread) { setMessages([]); return }
    void api<ChatMessage[]>(`/api/social/chats/${selectedThread.id}/messages`).then(setMessages)
  }, [selectedThread])

  const filteredFeed = useMemo(() => feed.filter((post) => !postQuery || `${post.content}${post.author?.display_name}${post.species?.common_name}${post.discovery?.title}`.toLowerCase().includes(postQuery.toLowerCase())), [feed, postQuery])

  const publish = async () => {
    if (!content.trim()) return
    await api('/api/social/posts', { method: 'POST', body: JSON.stringify({ content, image_url: postImageUrl, species_id: speciesId ? Number(speciesId) : null, visibility }) })
    setContent('')
    setPostImageUrl('')
    await load()
  }
  const uploadPostImage = async (file: File) => {
    setUploadingPostImage(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const result = await api<{ image_url: string }>('/api/social/attachments', { method: 'POST', body: form })
      setPostImageUrl(result.image_url)
    } finally {
      setUploadingPostImage(false)
    }
  }
  const requestFriend = async (name = username) => { if (!name.trim()) return; await api('/api/social/friends/request', { method: 'POST', body: JSON.stringify({ username: name.trim() }) }); setUsername(''); await load() }
  const accept = async (id: number) => { await api(`/api/social/friends/${id}/accept`, { method: 'POST' }); await load() }
  const removeFriend = async (id: number) => { await api(`/api/social/friends/${id}`, { method: 'DELETE' }); await load() }
  const like = async (id: number) => {
    const result = await api<{ likes: number; liked: boolean }>(`/api/social/posts/${id}/like`, { method: 'POST' })
    const patch = (items: FeedPost[]) => items.map((post) => post.id === id ? { ...post, likes: result.likes, liked_by_me: result.liked } : post)
    setFeed(patch)
    setRecommended(patch)
  }
  const createChat = async () => {
    const ids = groupMembers.map(Number).filter(Boolean)
    if (!ids.length) return
    const thread = await api<ChatThread>('/api/social/chats', { method: 'POST', body: JSON.stringify({ title: groupTitle, member_ids: ids }) })
    setSelectedThread(thread); setGroupMembers([]); setGroupTitle(''); await load()
  }
  const sendChat = async () => {
    if (!selectedThread || !chatText.trim()) return
    await api(`/api/social/chats/${selectedThread.id}/messages`, { method: 'POST', body: JSON.stringify({ content: chatText }) })
    setChatText('')
    setMessages(await api<ChatMessage[]>(`/api/social/chats/${selectedThread.id}/messages`))
  }

  return <div className="page-stack">
    <div className="page-intro"><div><span className="eyebrow">FOREST SOCIAL</span><h2>林间社群</h2><p>真实观察公开交流，好友申请双向提醒，按你观察过的物种和地点推荐相关内容。</p></div><button className="ghost-btn" onClick={() => setRefreshSeed((value) => value + 1)}><RefreshCw/>刷新推荐</button></div>
    <div className="community-layout">
      <main>
        <section className="panel composer"><div className="composer-title"><Avatar/><div><strong>发布真实观察或自然想法</strong><span>可发布文字和图片；公开内容会进入所有人的社群流。</span></div></div><textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="今天发现了什么？学到了什么？"/>{postImageUrl && <div className="composer-preview"><img src={mediaUrl(postImageUrl)} alt="帖子图片预览"/><button onClick={() => setPostImageUrl('')}><X size={16}/></button></div>}<div className="composer-actions"><select value={speciesId} onChange={(event) => setSpeciesId(event.target.value)}><option value="">关联物种（可选）</option>{species.map((item) => <option key={item.id} value={item.id}>{item.common_name} · {item.scientific_name}</option>)}</select><select value={visibility} onChange={(event) => setVisibility(event.target.value)}><option value="public">公开</option><option value="friends">好友可见</option><option value="private">仅自己</option></select><label className="ghost-btn upload-label"><ImagePlus/>{uploadingPostImage ? '上传中' : '添加图片'}<input type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(event) => event.target.files?.[0] && void uploadPostImage(event.target.files[0])}/></label><button className="primary-btn" onClick={() => void publish()}><Send/>发布</button></div></section>
        <section className="panel"><div className="panel-head"><div><span className="eyebrow">RECOMMENDED</span><h3>为你推荐 10 条真实动态</h3></div><RefreshCw onClick={() => setRefreshSeed((value) => value + 1)}/></div><div className="feed-list compact-feed">{recommended.map((post) => <FeedCard key={post.id} post={post} onLike={like}/>)}</div></section>
        <section className="panel"><div className="history-toolbar"><label className="search-box"><Search/><input value={postQuery} onChange={(event) => setPostQuery(event.target.value)} placeholder="搜索所有可见动态"/></label></div><div className="feed-list">{filteredFeed.map((post) => <FeedCard key={post.id} post={post} onLike={like}/>)}</div></section>
      </main>
      <aside className="panel friends-panel"><div className="panel-head"><div><span className="eyebrow">PEOPLE</span><h3>好友与聊天</h3></div><Users/></div>
        <div className="friend-add"><input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="输入用户名添加好友"/><button className="ghost-btn" onClick={() => void requestFriend()}><UserPlus/></button></div>
        <div className="friend-add"><input value={userQuery} onChange={(event) => setUserQuery(event.target.value)} placeholder="搜索用户"/>{userQuery && <button className="ghost-btn" onClick={() => setUserQuery('')}>清空</button>}</div>
        {users.map((item) => <div className="friend-row" key={item.id}><Avatar user={item}/><div><strong>{item.display_name}</strong><span>@{item.username} · Lv.{item.level} · {item.badges.join(' / ')}</span></div><button onClick={() => void requestFriend(item.username)}><UserPlus/></button></div>)}
        {pending.length > 0 && <div className="pending-box"><strong>新的好友申请</strong>{pending.map((item) => <button key={item.friendship_id} onClick={() => void accept(item.friendship_id)}><span>{item.user.display_name}</span>接受</button>)}</div>}
        <div className="friend-list">{friends.map((friend) => <div className="friend-row" key={friend.id}><Avatar user={friend}/><div><strong>{friend.display_name}</strong><span>Lv.{friend.level} · {friend.badges.join(' / ')}</span><small>{friend.bio}</small></div><button onClick={() => void removeFriend(friend.id)}><Trash2/></button></div>)}</div>
        <div className="pending-box"><strong><Bell size={15}/>提醒</strong>{notices.slice(0, 6).map((notice) => <button key={notice.id}><span>{notice.title}</span>{notice.read ? <CheckCircle2/> : '未读'}</button>)}</div>
        <div className="pending-box"><strong><MessageCircle size={15}/>聊天 / 群聊</strong><input value={groupTitle} onChange={(event) => setGroupTitle(event.target.value)} placeholder="群聊名称（可选）"/><select multiple value={groupMembers} onChange={(event) => setGroupMembers(Array.from(event.target.selectedOptions).map((option) => option.value))}>{friends.map((friend) => <option key={friend.id} value={friend.id}>{friend.display_name}</option>)}</select><button onClick={() => void createChat()}>创建聊天</button>{threads.map((thread) => <button key={thread.id} onClick={() => setSelectedThread(thread)}><span>{thread.title}</span>{thread.thread_type === 'group' ? '群聊' : '私聊'}</button>)}</div>
        {selectedThread && <div className="chat-box"><strong>{selectedThread.title}</strong><div className="chat-messages">{messages.map((message) => <div key={message.id}><b>{message.sender?.display_name || '用户'}：</b>{message.content}</div>)}</div><div className="qa-input"><input value={chatText} onChange={(event) => setChatText(event.target.value)} placeholder="输入消息"/><button onClick={() => void sendChat()}><Send/></button></div></div>}
      </aside>
    </div>
  </div>
}

function FeedCard({ post, onLike }: { post: FeedPost; onLike: (id: number) => Promise<void> }) {
  const [commentsOpen, setCommentsOpen] = useState(false)
  const [comments, setComments] = useState<FeedComment[]>(post.comments ?? [])
  const [commentText, setCommentText] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => setComments(post.comments ?? []), [post.id, post.comments])

  const toggleComments = async () => {
    const next = !commentsOpen
    setCommentsOpen(next)
    if (next) setComments(await api<FeedComment[]>(`/api/social/posts/${post.id}/comments`))
  }
  const sendComment = async () => {
    if (!commentText.trim()) return
    setSending(true)
    try {
      const item = await api<FeedComment>(`/api/social/posts/${post.id}/comments`, {
        method: 'POST',
        body: JSON.stringify({ content: commentText.trim() }),
      })
      setComments((current) => [...current, item])
      setCommentText('')
    } finally {
      setSending(false)
    }
  }

  return <article className="feed-card">
    <div className="feed-head"><Avatar user={post.author}/><div><strong>{post.author?.display_name || '未知用户'}</strong><span>Lv.{post.author?.level ?? 1} · {post.author?.badges?.join(' / ') || '探索者'} · {new Date(post.created_at).toLocaleString('zh-CN')}</span></div></div>
    {post.species && <div className="post-species" style={{ borderColor: post.species.color }}><span style={{ background: post.species.color }}/>{post.species.common_name}<em>{post.species.scientific_name}</em></div>}
    {post.discovery && <div className="post-species" style={{ borderColor: '#38f2ad' }}><span style={{ background: '#38f2ad' }}/>{post.discovery.title}</div>}
    <p>{post.content}</p>
    {post.image_url && <img className="feed-image" src={mediaUrl(post.image_url)} alt="动态图片"/>}
    <div className="feed-actions">
      <button className={post.liked_by_me ? 'liked' : ''} onClick={() => void onLike(post.id)}><Heart fill={post.liked_by_me ? 'currentColor' : 'none'}/> {post.likes}</button>
      <button onClick={() => void toggleComments()}><MessageCircle/> {commentsOpen ? '收起评论' : `评论 ${Math.max(post.comment_count, comments.length)}`}</button>
    </div>
    {commentsOpen && <div className="comment-box">
      <div className="comment-list">{comments.length ? comments.map((item) => <div key={item.id} className="comment-row"><Avatar user={item.author}/><div><strong>{item.author?.display_name || '用户'}</strong><p>{item.content}</p><span>{new Date(item.created_at).toLocaleString('zh-CN')}</span></div></div>) : <span className="empty-inline">还没有评论，来写第一条。</span>}</div>
      <div className="comment-input"><input value={commentText} onChange={(event) => setCommentText(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void sendComment() }} placeholder="写下你的观察或补充"/><button disabled={sending || !commentText.trim()} onClick={() => void sendComment()}><Send/></button></div>
    </div>}
  </article>
}
