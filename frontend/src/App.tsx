import { App as AntdApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AppLayout } from './layouts/AppLayout'
import { antdTheme } from './theme/tokens'

export default function App() {
  return (
    <ConfigProvider locale={zhCN} theme={antdTheme}>
      <AntdApp>
        <AppLayout />
      </AntdApp>
    </ConfigProvider>
  )
}
