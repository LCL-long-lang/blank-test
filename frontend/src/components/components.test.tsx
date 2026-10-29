import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { ChatMessage, Session } from '../types'
import { AssistantMessage } from './chat/AssistantMessage'
import { ChatInput } from './chat/ChatInput'
import { MarkdownText } from './chat/MarkdownText'
import { SqlBlock } from './chat/SqlBlock'
import { SessionItem } from './sidebar/SessionItem'

const wrap = (ui: ReactNode) => render(<AntdApp>{ui}</AntdApp>)

const session: Session = { id: 's1', title: '品类趋势', pinned: false, created_at: '', updated_at: '' }

function renderItem(over: Partial<Parameters<typeof SessionItem>[0]> = {}) {
  const props = {
    session, active: false, streaming: false,
    onSelect: vi.fn(), onRename: vi.fn(), onTogglePin: vi.fn(), onDelete: vi.fn(), ...over,
  }
  wrap(<SessionItem {...props} />)
  return props
}

describe('SessionItem', () => {
  it('点击选中；键盘 Enter 也能选中', async () => {
    const p = renderItem()
    await userEvent.click(screen.getByText('品类趋势'))
    expect(p.onSelect).toHaveBeenCalledWith('s1')
    screen.getByTestId('session-s1').focus()
    await userEvent.keyboard('{Enter}')
    expect(p.onSelect).toHaveBeenCalledTimes(2)
  })

  it('行内重命名：Enter 提交，Esc 取消', async () => {
    const p = renderItem()
    await userEvent.click(screen.getByLabelText('重命名'))
    const input = screen.getByLabelText('会话名称')
    await userEvent.clear(input)
    await userEvent.type(input, '区域对比{Enter}')
    expect(p.onRename).toHaveBeenCalledWith('s1', '区域对比')
    expect(p.onSelect).not.toHaveBeenCalled()

    await userEvent.click(screen.getByLabelText('重命名'))
    await userEvent.type(screen.getByLabelText('会话名称'), 'xxx{Escape}')
    expect(p.onRename).toHaveBeenCalledTimes(1)
  })

  it('删除需要二次确认', async () => {
    const p = renderItem()
    await userEvent.click(screen.getByLabelText('删除'))
    expect(p.onDelete).not.toHaveBeenCalled()
    const tip = await screen.findByRole('tooltip')
    await userEvent.click(within(tip).getByRole('button', { name: /删\s*除/ }))
    await waitFor(() => expect(p.onDelete).toHaveBeenCalledWith('s1'))
  })

  it('置顶按钮', async () => {
    const p = renderItem()
    await userEvent.click(screen.getByLabelText('置顶'))
    expect(p.onTogglePin).toHaveBeenCalledWith('s1')
  })
})

describe('ChatInput', () => {
  it('Enter 发送并清空，Shift+Enter 换行，空内容不发送', async () => {
    const onSend = vi.fn()
    wrap(<ChatInput streaming={false} onSend={onSend} onStop={vi.fn()} />)
    const box = screen.getByLabelText('输入问题')
    await userEvent.type(box, '   {Enter}')
    expect(onSend).not.toHaveBeenCalled()
    await userEvent.clear(box)
    await userEvent.type(box, '第一行{Shift>}{Enter}{/Shift}第二行')
    expect(onSend).not.toHaveBeenCalled()
    await userEvent.keyboard('{Enter}')
    expect(onSend).toHaveBeenCalledWith('第一行\n第二行')
    expect(box).toHaveValue('')
  })

  it('生成中显示停止按钮', async () => {
    const onStop = vi.fn()
    wrap(<ChatInput streaming onSend={vi.fn()} onStop={onStop} />)
    expect(screen.queryByLabelText('发送')).toBeNull()
    await userEvent.click(screen.getByLabelText('停止生成'))
    expect(onStop).toHaveBeenCalled()
  })

  it('禁用状态', () => {
    wrap(<ChatInput streaming={false} disabled onSend={vi.fn()} onStop={vi.fn()} />)
    expect(screen.getByLabelText('输入问题')).toBeDisabled()
  })
})

const ai = (over: Partial<ChatMessage>): ChatMessage => ({
  id: 'm1', role: 'assistant', content: '', status: 'done', createdAt: '', steps: [], sql: null, attempts: [],
  rowCount: null, hasChart: false, error: null, elapsedMs: null, question: '各区域销售额', ...over,
})

describe('AssistantMessage', () => {
  it('步骤、行数、查看图表、解读、耗时', async () => {
    const onShowChart = vi.fn()
    wrap(
      <AssistantMessage
        message={ai({
          steps: [{ key: 'execute', label: '执行查询', status: 'done', detail: '7 行' }],
          sql: 'SELECT 1', attempts: [{ sql: 'x', attempt: 1 }, { sql: 'SELECT 1', attempt: 2 }],
          rowCount: 7, hasChart: true, content: '华东 **第一**', elapsedMs: 4210,
        })}
        chartActive={false}
        onShowChart={onShowChart}
        onRetry={vi.fn()}
      />,
    )
    expect(screen.getByText('执行查询')).toBeInTheDocument()
    expect(screen.getByText('已自动修正')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('第一').tagName).toBe('STRONG')
    expect(screen.getByText('耗时 4.2s')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /查看图表/ }))
    expect(onShowChart).toHaveBeenCalledWith('m1')
  })

  it('错误卡片 + 重试', async () => {
    const onRetry = vi.fn()
    wrap(
      <AssistantMessage
        message={ai({ status: 'error', error: { code: 'SQL_FAILED', message: 'SQL 连续 3 次执行失败', retryable: true } })}
        chartActive={false}
        onShowChart={vi.fn()}
        onRetry={onRetry}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('SQL 连续 3 次执行失败')
    await userEvent.click(screen.getByRole('button', { name: /重试/ }))
    expect(onRetry).toHaveBeenCalledWith('m1')
  })

  it('已停止', () => {
    wrap(<AssistantMessage message={ai({ status: 'cancelled' })} chartActive={false} onShowChart={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByText('已停止生成')).toBeInTheDocument()
  })
})

describe('SqlBlock / MarkdownText', () => {
  it('SQL 默认折叠，点击展开后高亮显示', async () => {
    wrap(<SqlBlock sql="SELECT a FROM t" attempts={[{ sql: 'SELECT a FROM t', attempt: 1 }]} />)
    expect(screen.queryByText('SELECT')).toBeNull()
    await userEvent.click(screen.getByRole('button', { expanded: false }))
    expect(screen.getByText('SELECT')).toHaveClass('tok-kw')
    expect(screen.queryByText('已自动修正')).toBeNull()
  })

  it('模型输出的 HTML 不会被当作标签渲染', () => {
    const { container } = render(<MarkdownText text={'<img src=x onerror=alert(1)> **ok**'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>')
  })
})
