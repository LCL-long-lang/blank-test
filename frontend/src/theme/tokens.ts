/**
 * 科技风深色主题：深海军蓝底 + 青色辉光强调。
 * 图表系列色使用经 dataviz 校验的深色分类色板（对 #0f1626 面板：CVD ΔE ≥ 8.4、对比度 ≥ 3:1，全部通过），
 * 顺序固定，第 9 个系列不再生成新颜色。
 */
import { theme, type ThemeConfig } from 'antd'

export const colors = {
  bg: '#060b17',
  surface: '#0f1626',
  surfaceRaised: '#141d31',
  border: 'rgba(110, 180, 255, 0.14)',
  borderStrong: 'rgba(56, 219, 255, 0.45)',
  accent: '#38dbff',
  accent2: '#7c6cff',
  text: '#e6edf7',
  textSecondary: '#a3b1c6',
  textMuted: '#6b7a90',
  grid: '#1c2740',
  axis: '#2a3854',
  good: '#0ca30c',
  warning: '#fab219',
  critical: '#d03b3b',
} as const

export const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']

export const antdTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: colors.accent,
    colorInfo: colors.accent,
    colorBgBase: colors.bg,
    colorBgContainer: colors.surface,
    colorBgElevated: colors.surfaceRaised,
    colorBorder: colors.border,
    colorBorderSecondary: 'rgba(110, 180, 255, 0.08)',
    colorText: colors.text,
    colorTextSecondary: colors.textSecondary,
    colorTextTertiary: colors.textMuted,
    colorError: colors.critical,
    colorWarning: colors.warning,
    colorSuccess: colors.good,
    borderRadius: 8,
    fontFamily:
      "'Inter', system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    fontFamilyCode: "'JetBrains Mono', 'Cascadia Code', Consolas, monospace",
  },
  components: {
    Layout: { siderBg: 'transparent', bodyBg: 'transparent' },
    Button: { primaryColor: '#03121c', fontWeight: 600 },
    Table: { headerBg: colors.surfaceRaised, rowHoverBg: 'rgba(56, 219, 255, 0.06)', borderColor: colors.grid },
    Tabs: { itemSelectedColor: colors.accent, inkBarColor: colors.accent },
    Segmented: { itemSelectedBg: 'rgba(56, 219, 255, 0.16)', itemSelectedColor: colors.accent, trackBg: colors.bg },
    Input: { activeShadow: '0 0 0 2px rgba(56, 219, 255, 0.18)' },
    Splitter: { splitBarSize: 2, splitTriggerSize: 8 },
  },
}
