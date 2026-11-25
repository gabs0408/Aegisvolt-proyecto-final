
import { useEffect, useState } from 'react'

import {
  Zap,
  BatteryCharging,
  Activity,
  AlertCircle,
} from 'lucide-react'

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

import StatCard from './StatCard'
import { getLatestTelemetry } from '../services/telemetry'
import type { Telemetry } from '../services/telemetry'
import type { DispatchResult } from '../services/charging'

interface TelemetryPanelProps {
  dispatch: DispatchResult
}

interface ChartPoint {
  timestamp: string
  time: string
  power: number
  energy: number
}

export default function TelemetryPanel({
  dispatch,
}: TelemetryPanelProps) {
  const [telemetry, setTelemetry] =
    useState<Telemetry | null>(null)

  const [history, setHistory] =
    useState<ChartPoint[]>([])

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const dispatchId = dispatch.dispatch_id

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    async function loadTelemetry() {
      try {
        const data = await getLatestTelemetry(dispatchId)

        if (cancelled) return

        setTelemetry(data)
        setError('')

        setHistory(previous => {
          const last = previous[previous.length - 1]

          if (last?.timestamp === data.timestamp) {
            return previous
          }

          const point: ChartPoint = {
            timestamp: data.timestamp,
            time: new Date(
              data.timestamp,
            ).toLocaleTimeString(),
            power: Number(data.power_kw),
            energy: Number(data.energy_kwh),
          }

          return [...previous, point].slice(-150)
        })
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'Error al consultar la telemetría',
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)

          timer = setTimeout(() => {
            void loadTelemetry()
          }, 2000)
        }
      }
    }

    void loadTelemetry()

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [dispatchId])

  const lastMeasurement = telemetry
    ? new Date(telemetry.timestamp).toLocaleTimeString()
    : 'Sin mediciones'

  return (
    <section className="space-y-6">

      {/* Encabezado */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">
            Monitorización de carga
          </h2>

          <p className="mt-1 text-sm text-slate-400">
            {dispatch.connector_id} · Energy Dispatch Service
          </p>
        </div>

        <div className={`flex items-center gap-2 text-sm ${
          error ? 'text-red-400' : 'text-emerald-400'
        }`}>
          <span className={`h-2 w-2 rounded-full ${
            error
              ? 'bg-red-400'
              : 'animate-pulse bg-emerald-400'
          }`} />

          {error
            ? 'Error de consulta'
            : loading
              ? 'Conectando...'
              : 'Monitorización activa'}
        </div>
      </div>

      {/* Manejo de errores */}
      {error && (
        <div className="flex items-center gap-3 rounded-lg border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-400">
          <AlertCircle size={20} />
          {error}
        </div>
      )}

      {/* Indicadores */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">

        <StatCard
          title="Potencia registrada"
          value={telemetry
            ? `${Number(telemetry.power_kw).toFixed(2)} kW`
            : '—'}
          description="Última medición de potencia"
          icon={Zap}
          color="#34d399"
        />

        <StatCard
          title="Energía entregada"
          value={telemetry
            ? `${Number(telemetry.energy_kwh).toFixed(3)} kWh`
            : '—'}
          description="Consumo acumulado registrado"
          icon={BatteryCharging}
          color="#3b82f6"
        />

        <StatCard
          title="Último estado registrado"
          value={telemetry?.state || '—'}
          description="Estado reportado por la telemetría"
          icon={Activity}
          color="#a78bfa"
        />

      </div>

      {/* Información de la sesión */}
      <div className="rounded-xl border border-[#263449] bg-[#152135] p-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">

          <div>
            <p className="text-xs text-slate-400">
              Duración programada
            </p>

            <p className="mt-2 font-semibold">
              {dispatch.duration_seconds} segundos
            </p>
          </div>

          <div>
            <p className="text-xs text-slate-400">
              Última medición
            </p>

            <p className="mt-2 font-semibold">
              {lastMeasurement}
            </p>
          </div>

          <div>
            <p className="text-xs text-slate-400">
              Mediciones recopiladas
            </p>

            <p className="mt-2 font-semibold">
              {history.length}
            </p>
          </div>

        </div>
      </div>

      {/* Gráficas */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">

        <div className="rounded-xl border border-[#263449] bg-[#152135] p-6">

          <h3 className="text-lg font-semibold">
            Potencia durante la sesión
          </h3>

          <p className="mb-6 mt-1 text-sm text-slate-400">
            Potencia eléctrica registrada en kW
          </p>

          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history}>

                <defs>
                  <linearGradient
                    id="powerGradient"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stopColor="#34d399"
                      stopOpacity={0.35}
                    />
                    <stop
                      offset="100%"
                      stopColor="#34d399"
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>

                <CartesianGrid
                  stroke="#263449"
                  strokeDasharray="4 4"
                  vertical={false}
                />

                <XAxis
                  dataKey="time"
                  stroke="#94a3b8"
                  fontSize={10}
                />

                <YAxis
                  stroke="#94a3b8"
                  fontSize={11}
                  unit=" kW"
                />

                <Tooltip
                  contentStyle={{
                    backgroundColor: '#111b2d',
                    border: '1px solid #263449',
                    borderRadius: '8px',
                  }}
                  labelStyle={{ color: '#f1f5f9' }}
                />

                <Area
                  type="linear"
                  dataKey="power"
                  name="Potencia (kW)"
                  stroke="#34d399"
                  strokeWidth={3}
                  fill="url(#powerGradient)"
                  isAnimationActive={false}
                  dot={{ r: 2 }}
                />

              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl border border-[#263449] bg-[#152135] p-6">

          <h3 className="text-lg font-semibold">
            Energía acumulada
          </h3>

          <p className="mb-6 mt-1 text-sm text-slate-400">
            Energía entregada durante la carga
          </p>

          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history}>

                <defs>
                  <linearGradient
                    id="consumptionGradient"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stopColor="#3b82f6"
                      stopOpacity={0.35}
                    />
                    <stop
                      offset="100%"
                      stopColor="#3b82f6"
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>

                <CartesianGrid
                  stroke="#263449"
                  strokeDasharray="4 4"
                  vertical={false}
                />

                <XAxis
                  dataKey="time"
                  stroke="#94a3b8"
                  fontSize={10}
                />

                <YAxis
                  stroke="#94a3b8"
                  fontSize={11}
                  unit=" kWh"
                  width={80}
                />

                <Tooltip
                  contentStyle={{
                    backgroundColor: '#111b2d',
                    border: '1px solid #263449',
                    borderRadius: '8px',
                  }}
                  labelStyle={{ color: '#f1f5f9' }}
                />

                <Area
                  type="linear"
                  dataKey="energy"
                  name="Energía (kWh)"
                  stroke="#60a5fa"
                  strokeWidth={3}
                  fill="url(#consumptionGradient)"
                  isAnimationActive={false}
                  dot={{ r: 2 }}
                />

              </AreaChart>
            </ResponsiveContainer>
          </div>

        </div>

      </div>

      <div className="rounded-lg border border-[#263449] bg-[#111b2d] p-4">
        <p className="text-xs text-slate-400">
          Dispatch ID
        </p>

        <p className="mt-2 break-all font-mono text-xs text-slate-300">
          {dispatchId}
        </p>

        <p className="mt-3 text-xs text-slate-500">
          Consulta automática cada 2 segundos.
          Las gráficas muestran las últimas 150 mediciones
          diferentes recopiladas desde esta pantalla.
        </p>
      </div>

    </section>
  )
}
