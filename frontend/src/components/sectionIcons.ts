import {
  CalendarDays, CloudLightning, CloudSun, Droplets, Factory, Square, Trees, Users, Waves, Wheat,
  type LucideIcon,
} from 'lucide-react'

const ICONS: Record<string, LucideIcon> = {
  trees: Trees,
  droplets: Droplets,
  factory: Factory,
  waves: Waves,
  wheat: Wheat,
  'calendar-days': CalendarDays,
  'cloud-lightning': CloudLightning,
  'cloud-sun': CloudSun,
  users: Users,
}

/** The picture for a section, by the icon name the catalogue gives it; a plain square for a name not known. */
export function sectionIcon(name: string): LucideIcon {
  return ICONS[name] ?? Square
}
