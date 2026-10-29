/**
 * 应用级流程测试（Mock 模式）：新建会话 → 提问 → 步骤与流式文字 → 右栏出图 → 切换类型 → 切换历史会话。
 * services/index.ts 被替换为 Mock，不访问后端；ECharts 画布在 jsdom 中替换为占位组件。
 */
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 测试环境 VITE_USE_MOCK=true（见 vite.config.ts），services 自动使用 Mock
// jsdom 没有 canvas：把 ECharts 换成能读出 option 的占位
vi.mock('./components/chart/ChartView', async () => {
  const { forwardRef } = await import('react')
  return {
    ChartView: forwardRef<unknown, { option: Record<string, unknown> }>(function Fake({ option }, _ref) {
      const series = (option.series as Array<{ type: string; name?: string }>) ?? []
      return <div data-testid="chart-canvas" data-types={series.map((s) => s.type).join(',')}>{series.map((s) => s.name).join('|')}</div>
    }),
  }
})

import App from './App'
import { mockConfig, resetMock } from './mocks'
import { useChartStore } from './stores/chartStore'
import { useChatStore } from './stores/chatStore'
import { useSessionStore } from './stores/sessionStore'

/** Popconfirm 弹层里的确认按钮（antd 会在两个汉字间插入空格：“删 除”） */
async function confirmButton() {
  const tip = await screen.findByRole('tooltip')
  return within(tip).getByRole('button', { name: /删\s*除/ })
}

beforeEach(() => {
  resetMock()
  localStorage.clear()
  mockConfig.delay = 0
  useSessionStore.setState({ sessions: [], activeId: null, keyword: '', loading: false })
  useChatStore.setState({ messages: {}, streaming: null, controller: null, loadingSession: null })
  useChartStore.setState({ activeId: null, charts: {}, pendingData: {}, error: null, loadingId: null })
})

describe('App（Mock 模式）', () => {
  it('三栏布局与初始状态', async () => {
    render(<App />)
    expect(screen.getByTestId('panel-sessions')).toHaveTextContent('智能数据分析')
    expect(screen.getByTestId('panel-chat')).toHaveTextContent('问答区域')
    expect(screen.getByTestId('panel-chart')).toHaveTextContent('可视化图表')
    expect(await screen.findByText('大区销售排名')).toBeInTheDocument()
    expect(screen.getByText('置顶')).toBeInTheDocument()
    expect(screen.getByText('MOCK')).toBeInTheDocument()
    expect(await screen.findByText('后端已连接')).toBeInTheDocument()
    expect(screen.getByTestId('chart-empty')).toBeInTheDocument()
    expect(screen.getByText('用一句话，洞察你的业务数据')).toBeInTheDocument()
  })

  it('全流程：新建 → 点示例问题 → 流式回答 → 右栏出图 → 切换为柱状 → 数据表 → 切换会话', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('大区销售排名')

    await user.click(screen.getByRole('button', { name: /新建对话/ }))
    await user.click(await screen.findByRole('button', { name: /近 6 个月各品类销售额趋势/ }))

    const chat = screen.getByTestId('panel-chat')
    await waitFor(() => expect(within(chat).getByText(/手机数码/)).toBeInTheDocument())
    expect(within(chat).getByText('理解问题')).toBeInTheDocument()
    expect(within(chat).getByText((_, el) => el?.classList.contains('badge') === true && el.textContent === '共 24 行')).toBeInTheDocument()

    // 右栏：多系列折线
    const chartPanel = screen.getByTestId('panel-chart')
    const canvas = await within(chartPanel).findByTestId('chart-canvas')
    expect(canvas.dataset.types).toBe('line,line,line,line')
    expect(within(chartPanel).getByTestId('chart-title')).toHaveTextContent('近 6 个月各品类销售额趋势')

    // 标题自动更新
    expect(await within(screen.getByTestId('panel-sessions')).findByText('品类销售趋势')).toBeInTheDocument()

    // 切换为柱状图
    await user.click(within(chartPanel).getByLabelText('柱状'))
    await waitFor(() => expect(within(chartPanel).getByTestId('chart-canvas').dataset.types).toBe('bar,bar,bar,bar'))

    // 数据表
    await user.click(within(chartPanel).getByRole('tab', { name: /数据表/ }))
    expect(await within(chartPanel).findByRole('columnheader', { name: /category_name/ })).toBeInTheDocument()

    // 切到另一个历史会话再切回来，消息和图表都在
    await user.click(screen.getByText('会员等级占比'))
    await waitFor(() => expect(screen.getByText('用一句话，洞察你的业务数据')).toBeInTheDocument())
    await user.click(within(screen.getByTestId('panel-sessions')).getByText('品类销售趋势'))
    await waitFor(() => expect(within(chat).getByText(/手机数码/)).toBeInTheDocument())
    await waitFor(() => expect(within(chartPanel).getByTestId('chart-canvas')).toBeInTheDocument())
  })

  it('停止生成', async () => {
    mockConfig.delay = 40
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('大区销售排名')
    await user.type(screen.getByLabelText('输入问题'), '各会员等级的客户占比{Enter}')
    await user.click(await screen.findByLabelText('停止生成'))
    expect(await screen.findByText('已停止生成')).toBeInTheDocument()
    expect(screen.getByLabelText('发送')).toBeInTheDocument()
  })

  it('错误场景显示错误卡片，重试会重新提问', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('大区销售排名')
    await user.type(screen.getByLabelText('输入问题'), '故意让它失败{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('SQL 连续 3 次执行失败')
    await act(async () => {
      await user.click(screen.getByRole('button', { name: /重试/ }))
    })
    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(2))
  })

  it('KPI 用指标卡展示', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('大区销售排名')
    await user.type(screen.getByLabelText('输入问题'), '上个月总销售额是多少{Enter}')
    const chartPanel = screen.getByTestId('panel-chart')
    expect(await within(chartPanel).findByText('294.69万')).toBeInTheDocument()
    expect(within(chartPanel).queryByTestId('chart-canvas')).toBeNull()
  })

  it('删除会话', async () => {
    const user = userEvent.setup()
    render(<App />)
    const item = await screen.findByTestId('session-mock-s2')
    await user.click(within(item).getByLabelText('删除'))
    await user.click(await confirmButton())
    await waitFor(() => expect(screen.queryByTestId('session-mock-s2')).toBeNull())
  })
})
