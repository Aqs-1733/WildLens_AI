import { useEffect, useMemo, useState } from 'react'
import { BookOpen, CloudSun, Filter, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import SpeciesAvatar from '../components/SpeciesAvatar'
import SpeciesModal from '../components/SpeciesModal'
import type { Species } from '../types'
import { categoryNameZh, cleanChineseDisplayName, hasChinese, isUncertainName, localTaxonName } from '../utils/taxonNames'

const categories = [
  ['', '全部'],
  ['mammal', '哺乳动物'],
  ['bird', '鸟类'],
  ['plant', '植物'],
  ['insect', '昆虫'],
  ['reptile', '爬行动物'],
  ['amphibian', '两栖动物'],
]

function speciesDisplayName(species: Species): string {
  return cleanChineseDisplayName(
    localTaxonName({
      label: species.common_name,
      scientificName: species.scientific_name,
      category: species.category,
      fallback: species.common_name,
    }),
    species.common_name,
  )
}

function cleanBrief(species: Species): string {
  const text = (species.traits || species.ecology_value || species.habitat || '').trim()
  return /本地 BioCLIP|400721|资料生成中|待 AI|原型检索|具体分类单元|低置信度|候选/.test(text) ? '' : text
}

function validSpeciesCard(species: Species): boolean {
  const name = speciesDisplayName(species)
  return hasChinese(name) && !isUncertainName(name) && !isUncertainName(species.common_name)
}

export default function SpeciesPage() {
  const [items, setItems] = useState<Species[]>([])
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [selected, setSelected] = useState<number | null>(null)

  useEffect(() => { api<Species[]>('/api/species?mine=true').then(setItems) }, [])

  const filtered = useMemo(() => items.filter((item) => {
    const name = speciesDisplayName(item)
    const haystack = `${name}${item.common_name}${item.scientific_name}${item.english_name}`.toLowerCase()
    return validSpeciesCard(item) && (!category || item.category === category) && (!query || haystack.includes(query.toLowerCase()))
  }), [items, query, category])

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><span className="eyebrow">NATURE ATLAS</span><h2>自然图鉴</h2></div>
        <div className="search-box"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索中文名或学名" /></div>
      </div>
      <div className="mode-switch"><Link className="active" to="/species"><BookOpen />物种科普</Link><Link to="/collection"><Sparkles />物种收藏</Link><Link to="/classroom"><CloudSun />自然现象</Link></div>
      <div className="filter-row"><Filter size={17} />{categories.map(([value, label]) => <button className={category === value ? 'active' : ''} key={value} onClick={() => setCategory(value)}>{label}</button>)}</div>
      <div className="species-grid">
        {filtered.map((species) => {
          const brief = cleanBrief(species)
          const name = speciesDisplayName(species)
          return (
            <button className="species-card" key={species.id} onClick={() => setSelected(species.id)}>
              <div className="species-card-top"><SpeciesAvatar species={species} /><span className="rarity-stars">{'★'.repeat(species.rarity)}{'☆'.repeat(5 - species.rarity)}</span></div>
              <h3>{name}</h3>
              {brief && <p>{brief}</p>}
              <div className="species-card-foot"><span style={{ color: species.color }}>{categoryNameZh(species.category)}</span><span><ShieldCheck size={14} />{species.protection_level}</span></div>
            </button>
          )
        })}
      </div>
      {!filtered.length && <section className="panel empty-state">还没有可展示的中文图鉴条目。拍照识别、视频识别或在自然问答中确认具体物种后会自动加入。</section>}
      {selected && <SpeciesModal speciesId={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
