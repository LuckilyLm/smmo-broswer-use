import {
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DashboardSummary } from '../../api/dashboard'

type LeadTrend = DashboardSummary['lead_trend']
type IntentDistribution = DashboardSummary['intent_distribution']

export function DashboardLeadTrendChart({ data }: { data: LeadTrend }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="day" tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} />
        <Tooltip wrapperStyle={{ maxWidth: 'calc(100vw - 32px)' }} contentStyle={{ fontSize: 12, border: '1px solid var(--border)', borderRadius: 8 }} />
        <Line type="monotone" dataKey="leads" stroke="var(--primary)" strokeWidth={2} dot={false} name="线索" />
        <Line type="monotone" dataKey="scanned" stroke="var(--muted-foreground)" strokeWidth={1.5} dot={false} name="扫描量" strokeDasharray="4 2" />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function DashboardIntentChart({ data }: { data: IntentDistribution }) {
  return (
    <ResponsiveContainer width="100%" height={120}>
      <PieChart>
        <Pie data={data} cx="50%" cy="50%" innerRadius={30} outerRadius={52} dataKey="value" paddingAngle={2}>
          {data.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  )
}
