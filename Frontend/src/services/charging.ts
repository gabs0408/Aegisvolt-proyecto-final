
import { graphqlRequest } from './graphql'

export interface ChargingInput {
  correlationId: string
  fleetId: string
  connectorId: string
  estimatedAmountCents: number
  reservationDurationSeconds: number
  chargingDurationSeconds: number
}

export interface DispatchResult {
  dispatch_id: string
  reservation_id: string
  connector_id: string
  duration_seconds: number | string
  correlation_id: string
  status: string
  started_at: string
}

export interface SagaResult {
  correlation_id: string
  status: string
  step: string
  reservation?: unknown
  charge?: unknown
  dispatch?: DispatchResult | null
  refund?: unknown
  failure?: { step?: string; service?: string; message?: string; detail?: unknown } | null
  compensation_error?: unknown
}

const START_CHARGING = `
  mutation StartCharging($input: StartChargingSessionInput!) {
    startChargingSession(input: $input)
  }
`

const SAGA_STATUS = `
  query SagaStatus($correlationId: UUID!) {
    sagaStatus(correlationId: $correlationId)
  }
`

export async function startChargingSession(
  input: ChargingInput,
): Promise<SagaResult> {
  const data = await graphqlRequest<{
    startChargingSession: SagaResult
  }>(START_CHARGING, { input })

  return data.startChargingSession
}

export async function getSagaStatus(
  correlationId: string,
): Promise<SagaResult> {
  const data = await graphqlRequest<{
    sagaStatus: SagaResult
  }>(SAGA_STATUS, { correlationId })

  return data.sagaStatus
}
