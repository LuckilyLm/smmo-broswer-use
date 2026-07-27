import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend
} from 'recharts'
import { Zap, TrendingUp, Calendar, Download } from 'lucide-react'
import TopBar from '../components/layout/TopBar'

const dailyData = [
  { day: '7/17', input: 12400, output: 3200, total: 15600 },
  { day: '7/18', input: 18900, output: 4800, total: 23700 },
  { day: '7/19', input: 9800, output: 2500, total: 12300 },
  { day: '7/20', input: 22100, output: 5600, total: 27700 },
  { day: '7/21', input: 31400, output: 8100, total: 39500 },
  { day: '7/22', input: 19200, output: 5000, total: 24200 },
  { day: '7/23', input: 27800, output: 7100, total: 34900 },
]

const byCampaign = [
  { campaign: '跨境电商', tokens: 68400 },
  { campaign: '独立站获客', tokens: 41200 },
  { campaign: 'TikTok曝光', tokens: 29800 },
  { campaign: '海外招商', tokens: 18500 },
  { campaign: 'X高净值', tokens: 5700 },
]

const details = [
  { time: '07/23 10:12', campaign: '跨境电商引流', execution: 'EX-2847', model: 'claude-haiku-4-5', input: 4800, output: 1200, total: 6000, cost: 0.012 },
  { time: '07/23 09:48', campaign: '独立站获客', execution: 'EX-2846', model: 'claude-haiku-4-5', input: 3200, output: 800, total: 4000, cost: 0.008 },
  { time: '07/22 18:30', campaign: '海外招商合作', execution: 'EX-2843', model: 'claude-haiku-4-5', input: 5600, output: 1400, total: 7000, cost: 0.014 },
  { time: '07/22 14:15', campaign: '跨境电商引流', execution: 'EX-2841', model: 'claude-sonnet-4-6', input: 12000, output: 3000, total: 15000, cost: 0.075 },
]

export default function TokenUsage({ onMenuOpen }: { onMenuOpen?: () => void }) {
  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['运营管理', 'Token 用量']} pageTitle="Token 用量" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-5">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <h1 className="text-lg md:text-xl font-semibold text-gray-900">Token 用量</h1>
            <p className="text-sm text-gray-500 mt-0.5 hidden md:block">LLM 调用量统计，仅在启用 AI 功能时产生</p>
          </div>
          <div className="flex gap-2">
            <select className="px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
              <option>最近 7 天</option>
              <option>本月</option>
              <option>上月</option>
            </select>
            <button className="flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
              <Download size={14} /> 导出
            </button>
          </div>
        </div>

        {/* Metric cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: '今日 Token', value: '34,900', icon: <Zap size={14} />, sub: '输入 27,800 + 输出 7,100' },
            { label: '本月累计', value: '178,000', icon: <Calendar size={14} />, sub: '较上月 +12%' },
            { label: '最近 7 天', value: '177,900', icon: <TrendingUp size={14} />, sub: '日均 25,414' },
            { label: '估算费用', value: '$0.89', icon: <Zap size={14} />, sub: '本月至今' },
          ].map((m) => (
            <div key={m.label} className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs text-gray-500">{m.label}</div>
                <div className="p-1.5 rounded-lg" style={{ background: 'var(--accent)', color: 'var(--primary)' }}>{m.icon}</div>
              </div>
              <div className="text-xl font-bold text-gray-900">{m.value}</div>
              <div className="text-[11px] text-gray-400 mt-0.5">{m.sub}</div>
            </div>
          ))}
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="text-sm font-semibold text-gray-800 mb-1">每日 Token 趋势</div>
            <div className="text-xs text-gray-400 mb-3">最近 7 天</div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={dailyData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(v: any) => v.toLocaleString()} />
                <Line type="monotone" dataKey="input" stroke="#4338ca" strokeWidth={2} dot={false} name="输入" />
                <Line type="monotone" dataKey="output" stroke="#10b981" strokeWidth={2} dot={false} name="输出" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="text-sm font-semibold text-gray-800 mb-1">活动 Token 消耗</div>
            <div className="text-xs text-gray-400 mb-3">最近 7 天累计</div>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={byCampaign} layout="vertical" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <YAxis type="category" dataKey="campaign" tick={{ fontSize: 11, fill: '#6b7280' }} axisLine={false} tickLine={false} width={70} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(v: any) => v.toLocaleString()} />
                <Bar dataKey="tokens" fill="#4338ca" radius={[0, 4, 4, 0]} name="Token" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Details table */}
        <div className="bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
            <div className="text-sm font-semibold text-gray-800">调用明细</div>
            <div className="flex gap-2">
              <select className="px-3 py-1.5 text-xs border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)' }}>
                <option>全部活动</option>
              </select>
              <select className="px-3 py-1.5 text-xs border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)' }}>
                <option>全部模型</option>
              </select>
            </div>
          </div>
          {/* Desktop table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                  {['时间', '活动', '执行', '模型', '输入 Token', '输出 Token', '合计', '费用'].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {details.map((d, i) => (
                  <tr key={i} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                    <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">{d.time}</td>
                    <td className="px-4 py-3 text-xs text-gray-700">{d.campaign}</td>
                    <td className="px-4 py-3 text-xs font-mono text-gray-500">{d.execution}</td>
                    <td className="px-4 py-3 text-xs font-mono text-gray-500">{d.model}</td>
                    <td className="px-4 py-3 text-xs text-right text-gray-600">{d.input.toLocaleString()}</td>
                    <td className="px-4 py-3 text-xs text-right text-gray-600">{d.output.toLocaleString()}</td>
                    <td className="px-4 py-3 text-xs text-right font-medium text-gray-800">{d.total.toLocaleString()}</td>
                    <td className="px-4 py-3 text-xs text-right text-gray-500">${d.cost.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
