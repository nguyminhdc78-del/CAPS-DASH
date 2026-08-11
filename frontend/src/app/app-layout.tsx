import { Layout, Spin } from 'antd'
import { Suspense } from 'react'
import type { ReactNode } from 'react'
import { Outlet } from 'react-router'

import { AppHeaderBar } from './app-header-bar'
import { AppSiderMenu } from './app-sider-menu'

const { Content, Sider, Header } = Layout

export function AppLayout(): ReactNode {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth={64} width={220} theme="dark">
        <AppSiderMenu />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 16px' }}>
          <AppHeaderBar />
        </Header>
        <Content style={{ margin: 16 }}>
          {/* Routes are lazily loaded, so every navigation needs a boundary. */}
          <Suspense
            fallback={
              <div style={{ display: 'grid', placeItems: 'center', minHeight: '50vh' }}>
                <Spin size="large" />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  )
}

export function CenteredLayout({ children }: { children: ReactNode }): ReactNode {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Content style={{ display: 'grid', placeItems: 'center', padding: 16 }}>
        {children}
      </Content>
    </Layout>
  )
}
