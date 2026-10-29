/** 纯函数工具：分组、数字格式、CSV 导出 */
import type { Cell, Session } from '../types'

export type SessionGroupKey = 'pinned' | 'today' | 'week' | 'earlier'

export const GROUP_LABELS: Record<SessionGroupKey, string> = {
  pinned: '置顶',
  today: '今天',
  week: '近 7 天',
  earlier: '更早',
}

/** 生成与后端一致的本地时间戳 “YYYY-MM-DD HH:MM:SS”（不能用 toISOString，那是 UTC） */
export function localStamp(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 后端时间格式 “YYYY-MM-DD HH:MM:SS[.ffffff]” 是本地时间 */
export function parseStamp(s: string): Date {
  return new Date(s.replace(' ', 'T').slice(0, 19))
}

export function groupSessions(sessions: Session[], now = new Date()): Array<{ key: SessionGroupKey; items: Session[] }> {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const weekAgo = startOfToday - 6 * 86_400_000
  const groups: Record<SessionGroupKey, Session[]> = { pinned: [], today: [], week: [], earlier: [] }
  for (const s of sessions) {
    if (s.pinned) groups.pinned.push(s)
    else {
      const t = parseStamp(s.updated_at).getTime()
      groups[t >= startOfToday ? 'today' : t >= weekAgo ? 'week' : 'earlier'].push(s)
    }
  }
  return (Object.keys(groups) as SessionGroupKey[])
    .filter((k) => groups[k].length)
    .map((key) => ({ key, items: groups[key] }))
}

/** 千分位，最多 2 位小数 */
export function formatNumber(v: Cell): string {
  if (typeof v !== 'number') return v === null ? '—' : String(v)
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

/** 大数字压缩：12,900 → 1.29万；3,200,000 → 320万；1.2e8 → 1.2亿 */
export function compactNumber(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1e8) return `${+(v / 1e8).toFixed(2)}亿`
  if (abs >= 1e4) return `${+(v / 1e4).toFixed(2)}万`
  if (abs > 0 && abs < 1) return `${+(v * 100).toFixed(2)}%`
  return formatNumber(v)
}

export function toCsv(columns: string[], rows: Cell[][]): string {
  const esc = (v: Cell) => {
    const s = v === null ? '' : String(v)
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [columns, ...rows].map((r) => r.map(esc).join(',')).join('\r\n')
}

export function download(filename: string, content: Blob | string, type = 'text/csv;charset=utf-8') {
  // CSV 加 BOM，Excel 打开中文不乱码
  const blob = typeof content === 'string' ? new Blob(['﻿', content], { type }) : content
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function safeFilename(s: string) {
  return s.replace(/[\\/:*?"<>|]/g, '_').slice(0, 40) || 'chart'
}
