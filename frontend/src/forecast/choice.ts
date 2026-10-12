import type { ForecastCatalogue, ForecastLayer, ForecastTime } from '../api/types'

/** The one forecast on the map: a layer, the model and pressure level it is shown for, and the time. */
export interface ForecastChoice {
  layer: string
  model: string
  /** Pressure level in hPa; 0 is the surface. */
  level: number
  /** The time the forecast is for, UTC, as YYYYMMDDHH. Null until the available times are known. */
  time: string | null
}

/** Pakistan is five hours ahead of UTC all year. */
const PKT_OFFSET_HOURS = 5
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** A layer has current data when at least one model offers a level for it. */
export function hasData(layer: ForecastLayer): boolean {
  return Object.values(layer.levels).some((levels) => levels.length > 0)
}

export function levelsFor(layer: ForecastLayer, modelId: string): number[] {
  return layer.levels[modelId] ?? []
}

/**
 * The choice for a layer, keeping the model and level already on screen where the layer offers them,
 * so stepping through layers compares like with like. Null when the layer has no current data.
 */
export function chooseLayer(
  forecast: ForecastCatalogue,
  layerId: string,
  previous: ForecastChoice | null,
): ForecastChoice | null {
  const layer = forecast.layers.find((l) => l.id === layerId)
  if (!layer || !hasData(layer)) return null
  const keepModel = previous !== null && levelsFor(layer, previous.model).length > 0
  const model = keepModel ? previous.model : forecast.models.find((m) => levelsFor(layer, m.id).length > 0)?.id
  if (!model) return null
  return chooseModel(layer, model, previous)
}

/** The choice for a layer and model, keeping the level and time on screen where they still apply. */
export function chooseModel(layer: ForecastLayer, modelId: string, previous: ForecastChoice | null): ForecastChoice {
  const levels = levelsFor(layer, modelId)
  const level = previous !== null && levels.includes(previous.level) ? previous.level : (levels[0] ?? 0)
  return { layer: layer.id, model: modelId, level, time: previous?.time ?? null }
}

/** The values the ramp's two ends stand for, for a level and model. */
export function valueRange(layer: ForecastLayer, level: number, modelId = ''): [number, number] {
  return layer.model_ranges?.[modelId] ?? layer.ranges[String(level)] ?? [layer.min, layer.max]
}

/** The values to write under the key: every colour's value when they are unevenly spread, else the two ends. */
export function legendValues(layer: ForecastLayer, level: number, modelId = ''): number[] {
  return layer.stops?.length ? layer.stops : valueRange(layer, level, modelId)
}

/** A level's name. PMD files a few surface quantities under their height in metres, such as 2. */
export function levelLabel(level: number): string {
  if (level === 0) return 'Surface'
  return level < 50 ? `${level} m` : `${level} hPa`
}

export function hourToDate(time: string): Date {
  return new Date(
    Date.UTC(Number(time.slice(0, 4)), Number(time.slice(4, 6)) - 1, Number(time.slice(6, 8)), Number(time.slice(8, 10))),
  )
}

/** The available time closest to a moment; the later one when two are equally close. */
export function nearestTime(times: string[], now: Date): string | null {
  let best: string | null = null
  let bestGap = Infinity
  for (const time of times) {
    const gap = Math.abs(hourToDate(time).getTime() - now.getTime())
    if (gap <= bestGap) {
      best = time
      bestGap = gap
    }
  }
  return best
}

/** The model run a time is shown from, or null for a time not on offer. */
export function runOf(times: ForecastTime[], time: string | null): string | null {
  return times.find((t) => t.time === time)?.run ?? null
}

/** The next few times after one, in order; fewer near the end, none for a time not in the list. */
export function timesAhead(times: string[], current: string, count: number): string[] {
  const at = times.indexOf(current)
  return at < 0 ? [] : times.slice(at + 1, at + 1 + count)
}

/** A time in Pakistan's clock: "Mon 12 Oct, 17:00". */
export function formatTime(time: string): string {
  const local = new Date(hourToDate(time).getTime() + PKT_OFFSET_HOURS * 3600_000)
  const hour = String(local.getUTCHours()).padStart(2, '0')
  return `${DAYS[local.getUTCDay()]} ${local.getUTCDate()} ${MONTHS[local.getUTCMonth()]}, ${hour}:00`
}

/** A model run's time, which forecasters quote in UTC: "9 Oct 12:00 UTC". */
export function formatRun(run: string): string {
  const date = hourToDate(run)
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]} ${String(date.getUTCHours()).padStart(2, '0')}:00 UTC`
}

/** The choice as it appears in a link: layer~model~level~time. */
export function serializeChoice(choice: ForecastChoice): string {
  const parts = [choice.layer, choice.model, String(choice.level)]
  if (choice.time) parts.push(choice.time)
  return parts.join('~')
}

/** A choice read back from a link, or null when the layer list does not offer it. */
export function parseChoice(raw: string, forecast: ForecastCatalogue | null | undefined): ForecastChoice | null {
  if (!forecast) return null
  const [layerId, modelId, rawLevel, rawTime] = raw.split('~')
  const layer = forecast.layers.find((l) => l.id === layerId)
  const level = Number(rawLevel)
  if (!layer || !modelId || !rawLevel || !Number.isInteger(level) || !levelsFor(layer, modelId).includes(level)) {
    return null
  }
  const time = rawTime && /^\d{10}$/.test(rawTime) ? rawTime : null
  return { layer: layer.id, model: modelId, level, time }
}
