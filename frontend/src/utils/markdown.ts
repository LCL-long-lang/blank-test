/** 轻量 Markdown 解析（纯函数）：段落、有序 / 无序列表，以及行内 **加粗** 和 `代码` */

export type Block = { type: 'p'; lines: string[] } | { type: 'ul' | 'ol'; items: string[] }
export type InlineToken = { text: string; kind: 'strong' | 'code' | null }

export function parseBlocks(src: string): Block[] {
  const blocks: Block[] = []
  for (const raw of src.replace(/\r/g, '').split('\n')) {
    const line = raw.trim()
    const ul = /^[-*•]\s+(.*)$/.exec(line)
    const ol = /^\d+[.)、]\s*(.*)$/.exec(line)
    const last = blocks[blocks.length - 1]
    if (!line) {
      blocks.push({ type: 'p', lines: [] })
    } else if (ul || ol) {
      const type = ul ? 'ul' : 'ol'
      const text = (ul ?? ol)![1]
      if (last?.type === type) last.items.push(text)
      else blocks.push({ type, items: [text] })
    } else if (last?.type === 'p') {
      last.lines.push(line)
    } else {
      blocks.push({ type: 'p', lines: [line] })
    }
  }
  return blocks.filter((b) => (b.type === 'p' ? b.lines.length : b.items.length))
}

export function parseInline(text: string): InlineToken[] {
  const out: InlineToken[] = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ text: text.slice(last, m.index), kind: null })
    const tok = m[0]
    out.push(tok.startsWith('**') ? { text: tok.slice(2, -2), kind: 'strong' } : { text: tok.slice(1, -1), kind: 'code' })
    last = m.index + tok.length
  }
  if (last < text.length) out.push({ text: text.slice(last), kind: null })
  return out
}
