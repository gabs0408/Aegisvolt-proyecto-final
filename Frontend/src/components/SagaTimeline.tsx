
import {
  CheckCircle2,
  XCircle,
  Clock,
  RotateCcw,
  ShieldCheck,
} from 'lucide-react'

import type { SagaResult } from '../services/charging'

interface SagaTimelineProps {
  result: SagaResult
}

export default function SagaTimeline({
  result,
}: SagaTimelineProps) {
  const succeeded = result.status === 'SUCCEEDED'
  const compensated = result.status === 'COMPENSATED'

  const steps = [
    {
      title: 'Reserva del conector',
      service: 'Station Reservation Service',
      completed: Boolean(result.reservation),
      failed: result.failure?.service === 'reservation',
    },
    {
      title: 'Cobro de la billetera',
      service: 'Billing Wallet Service',
      completed: Boolean(result.charge),
      failed: result.failure?.service === 'billing',
    },
    {
      title: 'Activación de carga',
      service: 'Energy Dispatch Service',
      completed: Boolean(result.dispatch),
      failed: result.failure?.service === 'dispatch',
    },
    {
      title: 'Finalización de la transacción',
      service: 'SAGA Orchestrator Service',
      completed: succeeded || compensated,
      failed: false,
    },
  ]

  return (
    <section className="rounded-xl border border-[#263449] bg-[#152135] p-6">

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            Seguimiento de la transacción SAGA
          </h2>

          <p className="mt-1 text-sm text-slate-400">
            Resultado de la operación distribuida
          </p>
        </div>

        <span className={`rounded-full px-4 py-2 text-xs font-semibold ${
          succeeded
            ? 'bg-emerald-400/10 text-emerald-400'
            : compensated
              ? 'bg-amber-400/10 text-amber-400'
              : result.status === 'FAILED' ? 'bg-red-400/10 text-red-400' : 'bg-blue-400/10 text-blue-400'
        }`}>
          {result.status}
        </span>
      </div>

      <div className="space-y-4">
        {steps.map(step => (
          <div
            key={step.title}
            className="flex items-center gap-4 rounded-lg border border-[#263449] bg-[#111b2d] p-4"
          >
            {step.failed ? (
              <XCircle className="text-red-400" size={25} />
            ) : step.completed ? (
              <CheckCircle2 className="text-emerald-400" size={25} />
            ) : (
              <Clock className="text-slate-500" size={25} />
            )}

            <div className="flex-1">
              <h3 className="text-sm font-semibold">
                {step.title}
              </h3>

              <p className="mt-1 text-xs text-slate-400">
                {step.service}
              </p>
            </div>

            <span className={`text-xs ${
              step.failed
                ? 'text-red-400'
                : step.completed
                  ? 'text-emerald-400'
                  : 'text-slate-500'
            }`}>
              {step.failed
                ? 'Fallido'
                : step.completed
                  ? 'Completado'
                  : ['FAILED', 'COMPENSATED'].includes(result.status) ? 'No ejecutado' : 'Sin confirmar'}
            </span>
          </div>
        ))}
      </div>

      {result.failure && <p className="mt-4 text-sm text-red-400">{result.failure.message || result.failure.step}</p>}
      {compensated && (
        <div className="mt-6 rounded-lg border border-amber-400/20 bg-amber-400/5 p-4">
          <div className="flex items-center gap-2 text-amber-400">
            <RotateCcw size={20} />
            <h3 className="font-semibold">
              Compensación ejecutada
            </h3>
          </div>

          <p className="mt-2 text-sm text-slate-400">
            El orquestador reportó la finalización
            de la compensación.
          </p>

          <div className="mt-3 text-sm text-amber-300">
            {result.refund
              ? 'Reembolso registrado'
              : 'No se registró reembolso'}
          </div>
        </div>
      )}

      {succeeded && (
        <div className="mt-6 flex items-center gap-3 rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-4 text-sm text-emerald-400">
          <ShieldCheck size={24} />
          Transacción SAGA completada correctamente.
        </div>
      )}

      <div className="mt-6 border-t border-[#263449] pt-4">
        <p className="text-xs text-slate-400">
          Correlation ID
        </p>

        <p className="mt-2 break-all font-mono text-xs text-slate-300">
          {result.correlation_id}
        </p>
      </div>

      <details className="mt-5">
        <summary className="cursor-pointer text-sm text-emerald-400">
          Ver respuesta completa del backend
        </summary>

        <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-[#0b1120] p-4 text-xs text-slate-300">
          {JSON.stringify(result, null, 2)}
        </pre>
      </details>

    </section>
  )
}
