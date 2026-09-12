import { describe, expect, it } from 'vitest'
import {
  isInsideJsonDoubleString,
  shouldWrapAsJsonStringValue,
  wrapJsonStringValueIfNeeded,
} from '@/utils/jsonInsertWrap.js'

describe('jsonInsertWrap', () => {
  it('detects inside JSON string', () => {
    expect(isInsideJsonDoubleString('{"a":"')).toBe(true)
    expect(isInsideJsonDoubleString('{"a":')).toBe(false)
  })

  it('wraps after object colon', () => {
    expect(shouldWrapAsJsonStringValue('{"test":', '}')).toBe(true)
    expect(
      wrapJsonStringValueIfNeeded('${{token}}', '{"test":', '}')
    ).toBe('"${{token}}"')
  })

  it('wraps after array open', () => {
    expect(shouldWrapAsJsonStringValue('[', ']')).toBe(true)
  })

  it('does not wrap inside existing string', () => {
    expect(shouldWrapAsJsonStringValue('{"test":"', '"}')).toBe(false)
  })

  it('does not wrap when opening quote already typed', () => {
    expect(shouldWrapAsJsonStringValue('{"test":', ' "${{x}}"')).toBe(false)
  })
})
