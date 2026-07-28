import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

interface MetricCardProps {
  label: string
  value: string | number
  change?: number
  changeLabel?: string
  tooltip?: string
  icon?: React.ReactNode
  accent?: 'default' | 'warning' | 'success' | 'danger'
  sparkline?: number[]
}

export default function MetricCard({
  label, value, change, changeLabel, tooltip, icon, accent = 'default', sparkline
}: MetricCardProps) {
  const accentColors = {
    default: { icon: '#6366f1', bg: '#eef2ff' },
    warning: { icon: '#f59e0b', bg: '#fffbeb' },
    success: { icon: '#10b981', bg: '#ecfdf5' },
    danger: { icon: '#ef4444', bg: '#fef2f2' },
  }
  const color = accentColors[accent]

  const maxVal = sparkline ? Math.max(...sparkline, 1) : 1
  const minVal = sparkline ? Math.min(...sparkline) : 0

  return (
    <div
      className="group relative flex min-h-24 min-w-0 flex-col gap-2 rounded-xl border bg-card p-4"
      style={{ borderColor: 'var(--border)' }}
      title={tooltip}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 break-words text-[13px] font-medium leading-snug text-muted-foreground">{label}</div>
        {icon && (
          <div className="rounded-lg p-1.5 shrink-0" style={{ background: color.bg }}>
            <span style={{ color: color.icon }}>{icon}</span>
          </div>
        )}
      </div>
      <div className="flex items-end gap-3">
        <div className="whitespace-nowrap text-2xl font-bold leading-none text-foreground">{value}</div>
        {sparkline && sparkline.length > 1 && (
          <svg width={48} height={24} className="mb-0.5">
            <polyline
              points={sparkline.map((v, i) => {
                const x = (i / (sparkline.length - 1)) * 48
                const y = 24 - ((v - minVal) / (maxVal - minVal + 1)) * 20
                return `${x},${y}`
              }).join(' ')}
              fill="none"
              stroke={color.icon}
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </svg>
        )}
      </div>
      {change !== undefined && (
        <div className="flex items-center gap-1 text-xs">
          {change > 0
            ? <TrendingUp size={11} className="text-green-500" />
            : change < 0
              ? <TrendingDown size={11} className="text-red-400" />
              : <Minus size={11} className="text-gray-400" />
          }
          <span className={change > 0 ? 'text-green-600' : change < 0 ? 'text-red-500' : 'text-gray-400'}>
            {change > 0 ? '+' : ''}{change}
          </span>
          {changeLabel && <span className="text-gray-400">{changeLabel}</span>}
        </div>
      )}
    </div>
  )
}
