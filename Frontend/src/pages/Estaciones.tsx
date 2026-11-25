
import { useState, useEffect, useCallback } from 'react'
import {
  RefreshCw,
  PlugZap,
  CheckCircle2,
  Clock,
  AlertCircle,
} from 'lucide-react'

import ConnectorCard from '../components/ConnectorCard'
import StatCard from '../components/StatCard'
import { getStationStatus } from '../services/stations'
import type { ConnectorStatus } from '../services/stations'

const CONNECTOR_IDS = [
  'connector-1',
  'connector-2',
]

export default function Estaciones() {
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastUpdate, setLastUpdate] = useState('')

  const loadConnectors = useCallback(async () => {
    try {
      const results = await Promise.all(
        CONNECTOR_IDS.map(id => getStationStatus(id)),
      )

      setConnectors(results)
      setError('')
      setLastUpdate(new Date().toLocaleTimeString())
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'No fue posible consultar los conectores',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadConnectors()

    const interval = setInterval(() => {
      void loadConnectors()
    }, 5000)

    return () => clearInterval(interval)
  }, [loadConnectors])

  const available = connectors.filter(
    connector => connector.available,
  ).length

  const occupied = connectors.filter(
    connector => !connector.available,
  ).length

  return (
    <div className="space-y-7">

      {/* Encabezado */}
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">
            Estaciones de carga
          </h1>

          <p className="mt-2 text-sm text-slate-400">
            Gestión y disponibilidad de infraestructura eléctrica
          </p>
        </div>

        <button
          onClick={() => {
            setLoading(true)
            void loadConnectors()
          }}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-[#263449] bg-[#152135] px-5 py-3 text-sm font-medium hover:border-emerald-400 disabled:opacity-50"
        >
          <RefreshCw
            size={18}
            className={loading ? 'animate-spin' : ''}
          />
          Actualizar
        </button>
      </header>

      {/* Estado de conexión */}
      {error ? (
        <div className="flex items-center gap-3 rounded-lg border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-400">
          <AlertCircle size={20} />
          Error de conexión: {error}
        </div>
      ) : loading ? (
        <div className="rounded-lg border border-[#263449] bg-[#152135] p-4 text-sm text-slate-400">
          Consultando disponibilidad...
        </div>
      ) : (
        <div className="flex items-center justify-between rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-4">
          <div className="flex items-center gap-2 text-sm text-emerald-400">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
            Conectado al Gateway GraphQL
          </div>

          <span className="text-xs text-slate-400">
            Última actualización: {lastUpdate}
          </span>
        </div>
      )}

      {/* Indicadores */}
      <section className="grid grid-cols-1 gap-5 md:grid-cols-3">

        <StatCard
          title="Total de conectores"
          value={error || loading ? '—' : String(connectors.length)}
          description="Infraestructura consultada"
          icon={PlugZap}
          color="#3b82f6"
        />

        <StatCard
          title="Disponibles"
          value={error || loading ? '—' : String(available)}
          description="Listos para iniciar una carga"
          icon={CheckCircle2}
          color="#34d399"
        />

        <StatCard
          title="No disponibles"
          value={error || loading ? '—' : String(occupied)}
          description="Conectores no habilitados"
          icon={Clock}
          color="#fbbf24"
        />

      </section>

      {/* Conectores */}
      <section>
        <div className="mb-5">
          <h2 className="text-xl font-semibold">
            Conectores registrados
          </h2>

          <p className="mt-1 text-sm text-slate-400">
            Actualización automática cada 5 segundos
          </p>
        </div>

        {loading ? (
          <div className="rounded-xl border border-[#263449] bg-[#152135] p-10 text-center text-slate-400">
            Cargando conectores...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-[#263449] bg-[#152135] p-10 text-center text-slate-400">
            No se pudo verificar la disponibilidad.
            Intenta actualizar nuevamente.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {connectors.map(connector => (
              <ConnectorCard
                key={connector.connector_id}
                connector={connector}
              />
            ))}
          </div>
        )}
      </section>

    </div>
  )
}
