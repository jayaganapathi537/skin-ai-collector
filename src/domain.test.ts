import { describe, expect, it } from 'vitest'
import { CSV_COLUMNS, emptyAnnotation, escapeCsv, makeCsv } from './domain'

describe('labels1 CSV schema', () => {
  it('uses the exact required header and keeps blanks blank', () => {
    expect(CSV_COLUMNS.join(',')).toBe('person_id,photo_id,lighting,device,self_undertone,gold_or_silver,vein_colour,annotator1,annotator2,annotator3,final_label,skin_group')
    const row = {...emptyAnnotation(), person_id:'person-a', photo_id:'photo-a'}
    expect(makeCsv([row]).split('\r\n')[1]).toBe('person-a,photo-a,,,,,,,,,,')
  })
  it('escapes commas, quotes, and newlines according to CSV rules', () => {
    expect(escapeCsv('gold, "silver"\nunknown')).toBe('"gold, ""silver""\nunknown"')
  })
  it('emits one record per photo without inventing values', () => {
    const result = makeCsv([{person_id:'p1',photo_id:'a'},{person_id:'p2',photo_id:'b',lighting:'daylight'}])
    expect(result.split('\r\n')).toHaveLength(4)
    expect(result).toContain('p2,b,daylight,')
  })
})
