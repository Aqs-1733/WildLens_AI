import { Leaf, Radar } from 'lucide-react'

export default function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? 'brand-compact' : ''}`}>
      <div className="brand-mark"><Leaf size={23} /><Radar size={13} className="brand-radar" /></div>
      {!compact && <div><strong>识境</strong><span>Shijing AI</span></div>}
    </div>
  )
}
