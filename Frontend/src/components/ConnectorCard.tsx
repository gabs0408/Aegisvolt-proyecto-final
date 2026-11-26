
import {
  PlugZap,
  BatteryCharging,
  CheckCircle2,
  Clock,
} from 'lucide-react'

import { Link } from 'react-router-dom'
import type { ConnectorStatus } from '../services/stations'

interface ConnectorCardProps {
  connector: ConnectorStatus
}

export default function ConnectorCard({
  connector,
}: ConnectorCardProps) {
  const available = connector.available

  return (
    <article className="rounded-xl border border-[#263449] bg-[#152135] p-6 transition-colors hover:border-emerald-400/40">

      <div className="flex items-center justify-between">
        <div className="rounded-xl bg-emerald-400/10 p-4">
          <PlugZap
            size={30}
            className="text-emerald-400"
          />
        </div>

        <span
          className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${
            available
              ? 'bg-emerald-400/10 text-emerald-400'
              : 'bg-amber-400/10 text-amber-400'
          }`}
        >
          {available
            ? <CheckCircle2 size={14} />
            : <Clock size={14} />}

          {available ? 'Disponible' : 'No disponible'}
        </span>
      </div>

      <h2 className="mt-5 text-xl font-semibold text-white">
        {connector.connector_id}
      </h2>

      <p className="mt-1 text-sm text-slate-400">
        Punto de carga eléctrica
      </p>

      <div className="my-5 border-t border-[#263449]" />

      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-400">
          Estado operativo
        </span>

        <span className={
          available
            ? 'text-emerald-400'
            : 'text-amber-400'
        }>
          {connector.status}
        </span>
      </div>

      {available ? (
        <Link
          to={`/sesiones?connectorId=${encodeURIComponent(
            connector.connector_id,
          )}`}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-400 py-3 font-semibold text-slate-950 hover:bg-emerald-300"
        >
          <BatteryCharging size={19} />
          Iniciar carga
        </Link>
      ) : (
        <button
          disabled
          className="mt-6 w-full cursor-not-allowed rounded-lg bg-slate-700 py-3 text-slate-400"
        >
          Conector no disponible
        </button>
      )}

    </article>
  )
}
