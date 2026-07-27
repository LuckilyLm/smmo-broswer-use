import { useState } from 'react'
import Sidebar from './components/layout/Sidebar'
import Dashboard from './pages/Dashboard'
import Campaigns from './pages/Campaigns'
import CampaignSettings from './pages/CampaignSettings'
import ReplyTemplates from './pages/ReplyTemplates'
import MatchingRules from './pages/MatchingRules'
import ReplyTasks from './pages/ReplyTasks'
import ReplyRecords from './pages/ReplyRecords'
import LeadsInbox from './pages/LeadsInbox'
import PlatformAccounts from './pages/PlatformAccounts'
import ExecutionRecords from './pages/ExecutionRecords'
import Settings from './pages/Settings'
import Keywords from './pages/Keywords'
import TokenUsage from './pages/TokenUsage'
import Members from './pages/Members'
import AuditLog from './pages/AuditLog'
import NotificationCenter from './pages/NotificationCenter'
import SystemAdmin from './pages/SystemAdmin'

export default function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  const navigate = (page: string) => {
    setActivePage(page)
    setMobileSidebarOpen(false)
  }

  const renderPage = () => {
    const menuProps = { onMenuOpen: () => setMobileSidebarOpen(true) }
    switch (activePage) {
      case 'dashboard': return <Dashboard onNavigate={navigate} {...menuProps} />
      case 'campaigns': return <Campaigns onNavigate={navigate} {...menuProps} />
      case 'campaign-settings': return <CampaignSettings onNavigate={navigate} {...menuProps} />
      case 'reply-templates': return <ReplyTemplates {...menuProps} />
      case 'matching-rules': return <MatchingRules {...menuProps} />
      case 'reply-tasks': return <ReplyTasks {...menuProps} />
      case 'reply-records': return <ReplyRecords {...menuProps} />
      case 'leads-inbox': return <LeadsInbox {...menuProps} />
      case 'platform-accounts': return <PlatformAccounts {...menuProps} />
      case 'execution-records': return <ExecutionRecords {...menuProps} />
      case 'settings': return <Settings {...menuProps} />
      case 'keywords': return <Keywords {...menuProps} />
      case 'token-usage': return <TokenUsage {...menuProps} />
      case 'members': return <Members {...menuProps} />
      case 'audit-log': return <AuditLog {...menuProps} />
      case 'notifications': return <NotificationCenter onNavigate={navigate} {...menuProps} />
      case 'system-admin': return <SystemAdmin {...menuProps} />
      default: return <Dashboard onNavigate={navigate} {...menuProps} />
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar
        activePage={activePage}
        onNavigate={navigate}
        mobileOpen={mobileSidebarOpen}
        onMobileClose={() => setMobileSidebarOpen(false)}
      />
      <main className="flex-1 overflow-y-auto min-w-0">
        {renderPage()}
      </main>
    </div>
  )
}
