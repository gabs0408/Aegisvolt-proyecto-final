
import { graphqlRequest } from './graphql'

export interface Telemetry {
  dispatch_id: string
  connector_id: string
  timestamp: string
  power_kw: number
  energy_kwh: number
  state: string
}

const LATEST_TELEMETRY = `
  query LatestTelemetry($dispatchId: ID!) {
    latestTelemetry(dispatchId: $dispatchId)
  }
`

export async function getLatestTelemetry(
  dispatchId: string,
): Promise<Telemetry> {
  const data = await graphqlRequest<{
    latestTelemetry: Telemetry
  }>(LATEST_TELEMETRY, {
    dispatchId,
  })

  return data.latestTelemetry
}
