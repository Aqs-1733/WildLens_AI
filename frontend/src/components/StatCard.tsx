import type { LucideIcon } from 'lucide-react'

export default function StatCard({ label, value, hint, icon: Icon, tone = 'green' }: { label: string; value: string | number; hint: string; icon: LucideIcon; tone?: string }) {
  return <div className={`stat-card tone-${tone}`}><div className="stat-icon"><Icon size={22} /></div><div><span>{label}</span><strong>{value}</strong><small>{hint}</small></div></div>
}
