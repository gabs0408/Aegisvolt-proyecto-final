import { remember, save } from '../services/local'

import { useState } from 'react'
import type { FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'

import {
  BatteryCharging,
  Zap,
  AlertCircle,
  LoaderCircle,
  RefreshCw,
} from 'lucide-react'

import {
  startChargingSession,
  getSagaStatus,
} from '../services/charging'

import type { SagaResult } from '../services/charging'
import SagaTimeline from '../components/SagaTimeline'
import TelemetryPanel from '../components/TelemetryPanel'

const inputClass =
  'mt-2 w-full rounded-lg border border-[#334155] bg-[#111b2d] px-4 py-3 text-sm text-white outline-none focus:border-emerald-400'

export default function Sesiones() {
  const [searchParams] = useSearchParams()

  const [connectorId, setConnectorId] = useState(
    searchParams.get('connectorId') || 'connector-1',
  )

  const [fleetId, setFleetId] = useState('fleet-1')
  const [amount, setAmount] = useState(12)
  const [reservationDuration, setReservationDuration] = useState(300)
  const [chargingDuration, setChargingDuration] = useState(60)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<SagaResult | null>(null)
  const [correlationId, setCorrelationId] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (loading || correlationId) return

    setLoading(true)
    setError('')
    setResult(null)

    const id = crypto.randomUUID()
    setCorrelationId(id)
    remember(id)

    try {
      const response = await startChargingSession({
        correlationId: id,
        fleetId: fleetId.trim(),
        connectorId,
        estimatedAmountCents: Math.round(amount * 100),
        reservationDurationSeconds: reservationDuration,
        chargingDurationSeconds: chargingDuration,
      })

      setResult(response)
      save(response)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'No fue posible confirmar la sesión de carga',
      )
    } finally {
      setLoading(false)
    }
  }

  async function refreshStatus() {
    if (!correlationId || loading) return

    setLoading(true)
    setError('')

    try {
      const response = await getSagaStatus(correlationId)
      setResult(response)
      save(response)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'No fue posible consultar la transacción',
      )
    } finally {
      setLoading(false)
    }
  }

  function resetSession() {
    setResult(null)
    setError('')
    setCorrelationId('')
  }

  return (
    <div className="space-y-7">

      {/* Encabezado */}
      <header>
        <h1 className="text-3xl font-bold">
          Sesiones de carga
        </h1>

        <p className="mt-2 text-sm text-slate-400">
          Administración y seguimiento de cargas eléctricas
        </p>
      </header>

      <section className="grid grid-cols-1 items-start gap-6 xl:grid-cols-2">

        {/* Formulario */}
        <div className="rounded-xl border border-[#263449] bg-[#152135] p-6">

          <div className="mb-6 flex items-center gap-4">
            <div className="rounded-xl bg-emerald-400/10 p-4">
              <BatteryCharging
                size={30}
                className="text-emerald-400"
              />
            </div>

            <div>
              <h2 className="text-xl font-semibold">
                Nueva sesión de carga
              </h2>

              <p className="mt-1 text-sm text-slate-400">
                Configura los parámetros de la operación
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">

            <fieldset
              disabled={loading || Boolean(correlationId)}
              className="space-y-5 disabled:opacity-60"
            >

              <label className="block text-sm text-slate-300">
                Conector seleccionado

                <select
                  value={connectorId}
                  onChange={event => setConnectorId(event.target.value)}
                  className={inputClass}
                >
                  <option value="connector-1">Conector 01</option>
                  <option value="connector-2">Conector 02</option>
                </select>
              </label>

              <label className="block text-sm text-slate-300">
                Identificador de flota

                <input
                  type="text"
                  required
                  value={fleetId}
                  onChange={event => setFleetId(event.target.value)}
                  className={inputClass}
                />
              </label>

              <label className="block text-sm text-slate-300">
                Monto estimado

                <input
                  type="number"
                  required
                  min="0.01"
                  max="21474836.47"
                  step="0.01"
                  value={amount}
                  onChange={event => setAmount(Number(event.target.value))}
                  className={inputClass}
                />
              </label>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">

                <label className="block text-sm text-slate-300">
                  Duración de reserva (s)

                  <input
                    type="number"
                    required
                    min="1"
                    max="2147483647"
                    step="1"
                    value={reservationDuration}
                    onChange={event =>
                      setReservationDuration(Number(event.target.value))
                    }
                    className={inputClass}
                  />
                </label>

                <label className="block text-sm text-slate-300">
                  Duración de carga (s)

                  <input
                    type="number"
                    required
                    min="1"
                    max="2147483647"
                    step="1"
                    value={chargingDuration}
                    onChange={event =>
                      setChargingDuration(Number(event.target.value))
                    }
                    className={inputClass}
                  />
                </label>

              </div>

              <div className="rounded-lg border border-[#263449] bg-[#111b2d] p-4">
                <p className="text-xs text-slate-400">
                  Correlation ID
                </p>

                <p className="mt-2 break-all font-mono text-xs text-slate-300">
                  {correlationId || 'UUID generado automáticamente'}
                </p>
              </div>

            </fieldset>

            <button
              type="submit"
              disabled={loading || Boolean(correlationId)}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-400 px-5 py-3 font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <LoaderCircle size={20} className="animate-spin" />
              ) : (
                <Zap size={20} />
              )}

              {loading
                ? 'Procesando operación...'
                : 'Iniciar sesión de carga'}
            </button>

          </form>

          {/* Mensajes de error */}
          {error && (
            <div className="mt-5 flex items-start gap-3 rounded-lg border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-400">
              <AlertCircle size={20} className="shrink-0" />

              <div>
                <p>{error}</p>
                <p className="mt-2 text-xs">
                  Consulta el estado de la transacción antes
                  de intentar iniciar otra carga.
                </p>
              </div>
            </div>
          )}

          {/* Consultar estado SAGA */}
          {correlationId && (
            <button
              onClick={refreshStatus}
              disabled={loading}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-[#334155] px-5 py-3 text-sm text-slate-300 hover:border-emerald-400 disabled:opacity-50"
            >
              <RefreshCw size={18} />
              Consultar estado SAGA
            </button>
          )}

          {/* Preparar nueva sesión */}
          {result && !loading &&
            ['SUCCEEDED', 'COMPENSATED', 'FAILED'].includes(result.status) && (
              <button
                onClick={resetSession}
                className="mt-4 w-full rounded-lg border border-[#334155] px-5 py-3 text-sm text-slate-300 hover:border-emerald-400"
              >
                Preparar nueva sesión
              </button>
            )}

        </div>

        {/* Resultado SAGA */}
        {result ? (
          <SagaTimeline result={result} />
        ) : (
          <div className="flex min-h-96 flex-col items-center justify-center rounded-xl border border-[#263449] bg-[#152135] p-8 text-center">

            <div className="mb-5 rounded-full bg-emerald-400/10 p-6">
              <BatteryCharging
                size={45}
                className="text-emerald-400"
              />
            </div>

            <h2 className="text-xl font-semibold">
              Seguimiento SAGA
            </h2>

            <p className="mt-3 max-w-sm text-sm text-slate-400">
              {loading
                ? 'Consultando la operación distribuida...'
                : 'Inicia una sesión de carga para visualizar el resultado de la transacción.'}
            </p>

          </div>
        )}

      </section>

      {/* Panel de telemetría en tiempo real */}
      {result?.status === 'SUCCEEDED' && result.dispatch && (
        <TelemetryPanel
          key={result.dispatch.dispatch_id}
          dispatch={result.dispatch}
        />
      )}

    </div>
  )
}
