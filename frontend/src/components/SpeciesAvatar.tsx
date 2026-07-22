import { Bird, Bug, Flower2, PawPrint, Sprout } from 'lucide-react'
import type { Species } from '../types'

const icons = { plant: Sprout, bird: Bird, insect: Bug, mammal: PawPrint }

export default function SpeciesAvatar({ species, large = false }: { species: Species; large?: boolean }) {
  const Icon = icons[species.category as keyof typeof icons] || Flower2
  return <div className={`species-avatar ${large ? 'large' : ''}`} style={{'--species-color': species.color} as React.CSSProperties}>
    {species.image_url ? <img src={species.image_url} alt={species.common_name} /> : <><Icon size={large ? 62 : 32}/><span>{species.common_name.slice(0,2)}</span></>}
  </div>
}
