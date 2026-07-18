import { describe, expect, it } from 'vitest'
import { buildFillValue, detectFillValueMode } from '@/utils/fillValueMode.js'

describe('fillValueMode', () => {
  it('detects random_int mode', () => {
    expect(detectFillValueMode('${{random_int}}').mode).toBe('random_int')
  })

  it('detects unix timestamp mode', () => {
    expect(detectFillValueMode('${{timestamp}}').mode).toBe('timestamp')
  })

  it('detects legacy datetime mode', () => {
    expect(detectFillValueMode('${{now_time}}').mode).toBe('datetime')
  })

  it('detects prefix timestamp', () => {
    const parsed = detectFillValueMode('order_${{timestamp}}')
    expect(parsed.mode).toBe('prefix_timestamp')
    expect(parsed.prefix).toBe('order_')
  })

  it('builds prefix timestamp value', () => {
    expect(buildFillValue('prefix_timestamp', { prefix: 'auto_' })).toBe('auto_${{timestamp}}')
  })

  it('preserves leading and trailing spaces in fixed mode', () => {
    const parsed = detectFillValueMode('  admin ')
    expect(parsed.mode).toBe('fixed')
    expect(parsed.fixed).toBe('  admin ')
  })

  it('treats padded dynamic token as fixed text', () => {
    const parsed = detectFillValueMode('  ${{timestamp}} ')
    expect(parsed.mode).toBe('fixed')
    expect(parsed.fixed).toBe('  ${{timestamp}} ')
  })
})
