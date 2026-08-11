import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Vietnamese and English must define exactly the same keys.
 *
 * This is the only reliable defence against a half-translated interface. A
 * missing key does not crash - i18next quietly falls back, so an untranslated
 * string ships and nobody notices until a user does.
 */

const LOCALES_DIR = join(process.cwd(), 'src/core/i18n/locales')

function flattenKeys(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix]
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key),
  )
}

function keysFor(language: string): Map<string, string[]> {
  const dir = join(LOCALES_DIR, language)
  const result = new Map<string, string[]>()
  for (const file of readdirSync(dir).filter((name) => name.endsWith('.json'))) {
    const parsed: unknown = JSON.parse(readFileSync(join(dir, file), 'utf8'))
    result.set(file, flattenKeys(parsed).sort())
  }
  return result
}

describe('locale parity', () => {
  const vi = keysFor('vi')
  const en = keysFor('en')

  it('defines the same namespaces in both languages', () => {
    expect([...en.keys()].sort()).toEqual([...vi.keys()].sort())
  })

  it.each([...vi.keys()])('has identical keys in %s', (namespace) => {
    expect(en.get(namespace)).toEqual(vi.get(namespace))
  })

  it('has no empty translations', () => {
    for (const language of ['vi', 'en']) {
      const dir = join(LOCALES_DIR, language)
      for (const file of readdirSync(dir).filter((name) => name.endsWith('.json'))) {
        const parsed = JSON.parse(readFileSync(join(dir, file), 'utf8')) as Record<string, string>
        for (const [key, text] of Object.entries(parsed)) {
          expect(text, `${language}/${file}:${key} is empty`).not.toBe('')
        }
      }
    }
  })
})
