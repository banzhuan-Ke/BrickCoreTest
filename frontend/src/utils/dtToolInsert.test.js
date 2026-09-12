import { describe, expect, it } from 'vitest'
import { formatDtToolRef, quoteDtLiteral } from '@/utils/dtToolInsert.js'

describe('dtToolInsert', () => {
  it('prefers single quotes for fmt literal', () => {
    expect(quoteDtLiteral('%Y-%m-%d %H:%M:%S')).toBe("'%Y-%m-%d %H:%M:%S'")
  })

  it('falls back to double quotes when value contains apostrophe', () => {
    expect(quoteDtLiteral("it's")).toBe(`"it's"`)
  })

  it('builds date_format expression', () => {
    expect(
      formatDtToolRef('date_format', { fmt: '%Y-%m-%d %H:%M:%S' }, { paramModes: { fmt: 'literal' } })
    ).toBe("${{dt:date_format|fmt='%Y-%m-%d %H:%M:%S'}}")
  })
})
