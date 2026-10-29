import { BarChartOutlined, MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { Drawer, Grid, Splitter } from 'antd'
import { useEffect, useState } from 'react'
import { ChartPanel } from '../components/chart/ChartPanel'
import { ChatPanel } from '../components/chat/ChatPanel'
import { SessionSidebar } from '../components/sidebar/SessionSidebar'
import { useChartStore } from '../stores/chartStore'
import './AppLayout.css'

/**
 * 三栏布局：左 聊天管理（可折叠）/ 中 问答区域 / 右 可视化图表（可拖拽调宽）。
 * 窗口宽度 < 1200px（xl 以下）时，右栏改为抽屉，有新图表时自动弹出。
 */
export function AppLayout() {
  const screens = Grid.useBreakpoint()
  // 首次渲染 screens 为空对象：默认按宽屏处理，避免闪烁
  const wide = screens.xl ?? true
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // 窄屏下右栏切换到新的消息时自动弹出抽屉（订阅 store 变化，属于外部系统同步）
  useEffect(() => {
    if (wide) return
    return useChartStore.subscribe((s, prev) => {
      if (s.activeId && s.activeId !== prev.activeId) setDrawerOpen(true)
    })
  }, [wide])

  return (
    <div className={`app-shell${collapsed ? ' collapsed' : ''}`}>
      <aside className="app-sider glass" data-testid="panel-sessions" aria-label="聊天管理">
        {!collapsed && <SessionSidebar />}
        <button
          type="button"
          className="collapse-btn"
          aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
          onClick={() => setCollapsed((v) => !v)}
        >
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </button>
      </aside>

      <main className="app-main">
        {wide ? (
          <Splitter className="app-splitter">
            <Splitter.Panel min={420}>
              <div className="glass panel-shell"><ChatPanel /></div>
            </Splitter.Panel>
            <Splitter.Panel defaultSize="42%" min={360} max="65%">
              <div className="glass panel-shell"><ChartPanel /></div>
            </Splitter.Panel>
          </Splitter>
        ) : (
          <>
            <div className="glass panel-shell"><ChatPanel /></div>
            <button type="button" className="chart-fab" aria-label="打开图表" onClick={() => setDrawerOpen(true)}>
              <BarChartOutlined />
            </button>
            <Drawer
              open={drawerOpen}
              onClose={() => setDrawerOpen(false)}
              placement="right"
              size="min(92vw, 640px)"
              title={null}
              closable
              className="chart-drawer"
              styles={{ body: { padding: 0 } }}
            >
              <ChartPanel />
            </Drawer>
          </>
        )}
      </main>
    </div>
  )
}
