import { inject, provide } from 'vue'

export const ASSERTION_RESPONSE_LOCATE_KEY = Symbol('assertionResponseLocate')

/** @typedef {(expected: string) => boolean} AssertionResponseLocateFn */

export function provideAssertionResponseLocate(fn) {
  provide(ASSERTION_RESPONSE_LOCATE_KEY, fn)
}

/** @returns {AssertionResponseLocateFn | null} */
export function useAssertionResponseLocate() {
  return inject(ASSERTION_RESPONSE_LOCATE_KEY, null)
}
