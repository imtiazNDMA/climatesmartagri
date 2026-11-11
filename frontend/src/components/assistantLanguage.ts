import type { AssistantLanguage } from '../api/types'

const STORAGE_KEY = 'csa.assistant.language'

/** The language chosen in this browser, English until one is chosen or when storage is unavailable. */
export function storedLanguage(): AssistantLanguage {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'ur' ? 'ur' : 'en'
  } catch {
    return 'en'
  }
}

export function storeLanguage(language: AssistantLanguage) {
  try {
    window.localStorage.setItem(STORAGE_KEY, language)
  } catch {
    // The choice then lasts only for this page.
  }
}

/** The chat's own words in each language. Urdu wording is pending native review with the answers (#10). */
export const CHAT_TEXT = {
  en: {
    you: 'You',
    guide: 'Guide',
    sources: 'Sources:',
    intro: 'Ask about the current map, a portal section, indicators, forecasts, or hazard guidance.',
    suggestions: null,
    thinking: 'Qwen is thinking…',
    unchecked: 'A figure in this answer could not be checked against the facts used.',
    uncheckedList: 'Unchecked:',
    placeholder: 'Ask about this portal…',
    question: 'Question for the portal guide',
    send: 'Send question',
  },
  ur: {
    you: 'آپ',
    guide: 'رہنما',
    sources: 'ذرائع:',
    intro: 'موجودہ نقشے، پورٹل کے کسی حصے، اشاریوں، موسمی پیشگوئی یا خطرات کی رہنمائی کے بارے میں پوچھیں۔',
    suggestions: [
      'اس پورٹل میں کون سی معلومات دستیاب ہیں؟',
      'خطرات کے رنگوں کی وضاحت کریں۔',
      'میں کسی ضلع کو کیسے دیکھوں؟',
    ],
    thinking: 'رہنما جواب تیار کر رہا ہے…',
    unchecked: 'اس جواب کا ایک عدد استعمال شدہ حقائق سے جانچا نہیں جا سکا۔',
    uncheckedList: 'غیر جانچ شدہ:',
    placeholder: 'پورٹل کے بارے میں پوچھیں…',
    question: 'پورٹل رہنما کے لیے سوال',
    send: 'سوال بھیجیں',
  },
} as const
