/**
 * 渲染模型解读文字。解析在 utils/markdown.ts；这里全部生成 React 节点（不使用 dangerouslySetInnerHTML），
 * 模型输出里的 HTML 会按纯文本显示。
 */
import { Fragment } from 'react'
import { parseBlocks, parseInline } from '../../utils/markdown'

function Inline({ text }: { text: string }) {
  return (
    <>
      {parseInline(text).map((t, i) =>
        t.kind === 'strong' ? <strong key={i}>{t.text}</strong> : t.kind === 'code' ? <code key={i}>{t.text}</code> : t.text,
      )}
    </>
  )
}

export function MarkdownText({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const blocks = parseBlocks(text)
  return (
    <div className="md">
      {blocks.map((b, bi) => {
        const caret = streaming && bi === blocks.length - 1 ? <span className="caret" aria-hidden /> : null
        if (b.type === 'p') {
          return (
            <p key={bi}>
              {b.lines.map((l, li) => (
                <Fragment key={li}>
                  {li > 0 && <br />}
                  <Inline text={l} />
                </Fragment>
              ))}
              {caret}
            </p>
          )
        }
        const List = b.type
        return (
          <List key={bi}>
            {b.items.map((it, ii) => (
              <li key={ii}>
                <Inline text={it} />
                {ii === b.items.length - 1 && caret}
              </li>
            ))}
          </List>
        )
      })}
      {streaming && blocks.length === 0 && <span className="caret" aria-hidden />}
    </div>
  )
}
