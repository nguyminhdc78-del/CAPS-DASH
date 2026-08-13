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
      <Sider breakpoint="lg" collapsedWidth={64} width={228} theme="dark" className="droom-sider">
        <AppSiderMenu />
      </Sider>
      <Layout>
        <Header className="droom-header" style={{ padding: '0 20px' }}>
          <AppHeaderBar />
        </Header>
        <Content className="droom-content" style={{ margin: 20 }}>
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

export function CenteredLayout({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}): ReactNode {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Content className={className} style={{ display: 'grid', placeItems: 'center', padding: 16 }}>
        {children}
      </Content>
    </Layout>
  )
}
