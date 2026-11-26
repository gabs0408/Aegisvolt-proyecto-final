
import type { LucideIcon } from 'lucide-react'

interface StatCardProps {
  title: string
  value: string
  description: string
  icon: LucideIcon
  color: string
}

export default function StatCard({
  title,
  value,
  description,
  icon: Icon,
  color,
}: StatCardProps) {
  return (
    <div className="rounded-xl border border-[#263449] bg-[#152135] p-5 transition-colors hover:border-emerald-400/40">

      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">
          {title}
        </p>

        <div
          className="rounded-lg p-3"
          style={{
            color,
            backgroundColor: `${color}15`,
          }}
        >
          <Icon size={22} />
        </div>
      </div>

      <h2 className="mt-3 text-3xl font-bold text-white">
        {value}
      </h2>

      <p className="mt-2 text-xs text-slate-400">
        {description}
      </p>
    </div>
  )
}
