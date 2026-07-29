export const BEIJING_TIME_ZONE = 'Asia/Shanghai'

type DateInput = string | number | Date | null | undefined

function toDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === '') return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatBeijingDateTime(value: DateInput): string {
  const date = toDate(value)
  if (!date) return ''
  return date.toLocaleString('zh-CN', {
    timeZone: BEIJING_TIME_ZONE,
    hour12: false,
  })
}

export function formatBeijingDate(value: DateInput, options: Intl.DateTimeFormatOptions = {}): string {
  const date = toDate(value)
  if (!date) return ''
  return date.toLocaleDateString('zh-CN', {
    timeZone: BEIJING_TIME_ZONE,
    ...options,
  })
}
