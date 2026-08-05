import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export interface DailyTokenUsage {
  day: string
  input: number
  output: number
  total: number
}

export interface CampaignTokenUsage {
  campaign: string
  tokens: number
}

export function DailyTokenChart({ data }: { data: DailyTokenUsage[] }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
        <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(value) => Number(value).toLocaleString()} />
        <Line type="monotone" dataKey="input" stroke="#4338ca" strokeWidth={2} dot name="输入" />
        <Line type="monotone" dataKey="output" stroke="#10b981" strokeWidth={2} dot name="输出" />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function CampaignTokenChart({ data }: { data: CampaignTokenUsage[] }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="campaign" tick={{ fontSize: 11, fill: '#6b7280' }} axisLine={false} tickLine={false} width={110} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(value) => Number(value).toLocaleString()} />
        <Bar dataKey="tokens" fill="#4338ca" radius={[0, 4, 4, 0]} name="Token" />
      </BarChart>
    </ResponsiveContainer>
  )
}
