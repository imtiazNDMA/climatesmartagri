import { describe, expect, it } from 'vitest'
import type { ForecastCatalogue } from '../api/types'
import {
  chooseLayer, chooseModel, formatRun, formatTime, hasData, legendValues, levelLabel, nearestTime, runOf, timeAtShare, timesAhead, parseChoice, serializeChoice,
  valueRange,
} from './choice'

const forecast: ForecastCatalogue = {
  configured: true,
  bbox: [55, 18, 85, 42],
  models: [
    { id: 'model-a', label: 'Model A' },
    { id: 'model-b', label: 'Model B' },
  ],
  groups: [{ id: 'heat', title: 'Heat' }],
  layers: [
    {
      id: 'temperature', title: 'Temperature', group: 'heat', unit: '°C', colours: ['#00f', '#f00'], min: 0, max: 40,
      ranges: { '500': [-40, 0] }, levels: { 'model-a': [0, 500], 'model-b': [0] },
    },
    {
      id: 'dew-point', title: 'Dew point', group: 'heat', unit: '°C', colours: ['#00f', '#f00'], min: 0, max: 30,
      ranges: {}, levels: { 'model-b': [0, 850] },
    },
    {
      id: 'old-only', title: 'Old only', group: 'heat', unit: '', colours: ['#00f', '#f00'], min: 0, max: 1,
      ranges: {}, levels: {},
    },
  ],
}
const [temperature, dewPoint, oldOnly] = forecast.layers

describe('choosing a layer', () => {
  it('starts with the first model that offers the layer, at its first level', () => {
    expect(chooseLayer(forecast, 'temperature', null)).toEqual({
      layer: 'temperature', model: 'model-a', level: 0, time: null,
    })
    expect(chooseLayer(forecast, 'dew-point', null)?.model).toBe('model-b')
  })

  it('keeps the model, level and time on screen when the new layer offers them', () => {
    const previous = { layer: 'dew-point', model: 'model-b', level: 0, time: '2026101200' }
    expect(chooseLayer(forecast, 'temperature', previous)).toEqual({
      layer: 'temperature', model: 'model-b', level: 0, time: '2026101200',
    })
  })

  it('moves to a model and level the layer does offer when the ones on screen are not', () => {
    const previous = { layer: 'temperature', model: 'model-a', level: 500, time: null }
    expect(chooseLayer(forecast, 'dew-point', previous)).toEqual({
      layer: 'dew-point', model: 'model-b', level: 0, time: null,
    })
  })

  it('gives nothing for a layer with no current data or one that is not listed', () => {
    expect(hasData(oldOnly)).toBe(false)
    expect(chooseLayer(forecast, 'old-only', null)).toBeNull()
    expect(chooseLayer(forecast, 'nope', null)).toBeNull()
  })
})

describe('choosing a model', () => {
  it('keeps the level when the model has it and falls back to its first when not', () => {
    const at500 = { layer: 'temperature', model: 'model-a', level: 500, time: '2026101200' }
    expect(chooseModel(temperature, 'model-b', at500)).toEqual({
      layer: 'temperature', model: 'model-b', level: 0, time: '2026101200',
    })
    expect(chooseModel(dewPoint, 'model-b', { ...at500, level: 850 }).level).toBe(850)
  })
})

describe('ranges and labels', () => {
  it('uses the range a level has of its own', () => {
    expect(valueRange(temperature, 0)).toEqual([0, 40])
    expect(valueRange(temperature, 500)).toEqual([-40, 0])
    const own = { ...temperature, model_ranges: { 'model-b': [5, 25] as [number, number] } }
    expect(valueRange(own, 500, 'model-b')).toEqual([5, 25])
    expect(valueRange(own, 500, 'model-a')).toEqual([-40, 0])
    expect(legendValues(own, 0, 'model-b')).toEqual([5, 25])
  })

  it('writes every colour’s value under a key with uneven stops, and the two ends otherwise', () => {
    expect(legendValues(temperature, 500)).toEqual([-40, 0])
    expect(legendValues({ ...temperature, stops: [0, 1, 10, 40] }, 0)).toEqual([0, 1, 10, 40])
  })

  it('names the surface and pressure levels', () => {
    expect(levelLabel(0)).toBe('Surface')
    expect(levelLabel(850)).toBe('850 hPa')
    expect(levelLabel(2)).toBe('2 m')
  })
})

describe('times', () => {
  const times = ['2026101100', '2026101112', '2026101200']

  it('picks the available time closest to now', () => {
    expect(nearestTime(times, new Date(Date.UTC(2026, 9, 11, 10)))).toBe('2026101112')
    expect(nearestTime(times, new Date(Date.UTC(2026, 9, 20)))).toBe('2026101200')
    expect(nearestTime(times, new Date(Date.UTC(2026, 9, 1)))).toBe('2026101100')
    expect(nearestTime([], new Date())).toBeNull()
  })

  it('takes the later of two equally close times', () => {
    expect(nearestTime(times, new Date(Date.UTC(2026, 9, 11, 6)))).toBe('2026101112')
  })

  it('writes a forecast time in the clock of Pakistan, five hours ahead of UTC', () => {
    expect(formatTime('2026101212')).toBe('Mon 12 Oct, 17:00')
    expect(formatTime('2026101221')).toBe('Tue 13 Oct, 02:00')
  })

  it('lists the times just ahead of one', () => {
    expect(timesAhead(times, '2026101100', 2)).toEqual(['2026101112', '2026101200'])
    expect(timesAhead(times, '2026101112', 2)).toEqual(['2026101200'])
    expect(timesAhead(times, '2026101200', 2)).toEqual([])
    expect(timesAhead(times, '2026010100', 2)).toEqual([])
  })

  it('finds the run a time is shown from', () => {
    const offered = [{ time: '2026101100', run: '2026100912' }, { time: '2026101112', run: '2026101000' }]
    expect(runOf(offered, '2026101112')).toBe('2026101000')
    expect(runOf(offered, '2026101200')).toBeNull()
    expect(runOf(offered, null)).toBeNull()
  })

  it('finds the hour part of the way between two times, across a midnight and a month end', () => {
    expect(timeAtShare('2026103118', '2026110106', 0)).toBe('2026103118')
    expect(timeAtShare('2026103118', '2026110106', 0.5)).toBe('2026110100')
    expect(timeAtShare('2026103118', '2026110106', 0.75)).toBe('2026110103')
    expect(timeAtShare('2026103118', '2026110106', 1)).toBe('2026110106')
    expect(timeAtShare('2026110106', '2026103118', 0.5)).toBe('2026110100') // backwards too
  })

  it('writes a run time in UTC', () => {
    expect(formatRun('2026100912')).toBe('9 Oct 12:00 UTC')
  })
})

describe('the choice in a link', () => {
  it('round-trips with and without a time', () => {
    const withTime = { layer: 'temperature', model: 'model-a', level: 500, time: '2026101200' }
    expect(serializeChoice(withTime)).toBe('temperature~model-a~500~2026101200')
    expect(parseChoice(serializeChoice(withTime), forecast)).toEqual(withTime)
    const noTime = { ...withTime, time: null }
    expect(serializeChoice(noTime)).toBe('temperature~model-a~500')
    expect(parseChoice(serializeChoice(noTime), forecast)).toEqual(noTime)
  })

  it('refuses a layer, model or level the list does not offer, and drops a malformed time', () => {
    expect(parseChoice('nope~model-a~0', forecast)).toBeNull()
    expect(parseChoice('temperature~model-z~0', forecast)).toBeNull()
    expect(parseChoice('temperature~model-b~500', forecast)).toBeNull()
    expect(parseChoice('temperature~model-a~x', forecast)).toBeNull()
    expect(parseChoice('temperature~model-a', forecast)).toBeNull()
    expect(parseChoice('temperature~model-a~0~soon', forecast)?.time).toBeNull()
    expect(parseChoice('temperature~model-a~0', null)).toBeNull()
  })
})
