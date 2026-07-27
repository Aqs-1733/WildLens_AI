import {
  Bird,
  Bug,
  Cat,
  CloudSun,
  Feather,
  Fish,
  Flame,
  Flower2,
  Leaf,
  PawPrint,
  Rabbit,
  Shell,
  Snowflake,
  Sprout,
  TreePine,
  Turtle,
  Waves,
  type LucideIcon,
} from 'lucide-react'
import type { Species } from '../types'

const iconGroups: Record<string, LucideIcon[]> = {
  mammal: [PawPrint, Cat, Rabbit],
  bird: [Bird, Feather],
  insect: [Bug],
  reptile: [Turtle],
  amphibian: [Turtle],
  fish: [Fish],
  mollusk: [Shell],
  crustacean: [Shell],
  invertebrate: [Bug, Shell],
  plant: [Sprout, Leaf, TreePine, Flower2],
  angiosperm: [Flower2, Leaf],
  gymnosperm: [TreePine, Sprout],
  fern: [Leaf, Sprout],
  moss: [Sprout],
  algae: [Waves, Leaf],
  fungus: [Sprout],
  lichen: [Leaf],
  phenomenon: [CloudSun, Waves, Snowflake],
  weather: [CloudSun, Snowflake],
  fire: [Flame],
  smoke: [CloudSun],
}

function hashText(value: string): number {
  return Array.from(value).reduce((total, char) => (total * 31 + char.charCodeAt(0)) >>> 0, 17)
}

function isPlaceholderImage(value: string): boolean {
  return /\/?showcase_[^/]+\.png$/i.test(value.trim())
}

export default function SpeciesAvatar({ species, large = false }: { species: Species; large?: boolean }) {
  const seed = hashText(`${species.scientific_name}:${species.common_name}:${species.category}`)
  const options = iconGroups[species.category] || [Flower2]
  const Icon = options[seed % options.length]
  const imageUrl = species.image_url?.trim()
  const hasRealImage = Boolean(imageUrl && !isPlaceholderImage(imageUrl))
  const pattern = `pattern-${seed % 4}`
  return (
    <div
      className={`species-avatar ${large ? 'large' : ''} ${hasRealImage ? 'photo' : `fallback ${pattern}`}`}
      style={{ '--species-color': species.color } as React.CSSProperties}
    >
      {hasRealImage ? (
        <img src={imageUrl} alt={species.common_name} loading="lazy" />
      ) : (
        <>
          <Icon size={large ? 60 : 30} />
          <span className="avatar-initials">{species.common_name.slice(0, 2)}</span>
        </>
      )}
    </div>
  )
}
