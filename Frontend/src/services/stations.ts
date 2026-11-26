
import { graphqlRequest } from './graphql'

export interface ConnectorStatus {
  connector_id: string
  available: boolean
  status: string
}

const STATION_STATUS = `
  query StationStatus($connectorId: String!) {
    stationStatus(connectorId: $connectorId)
  }
`

export async function getStationStatus(
  connectorId: string,
): Promise<ConnectorStatus> {
  const data = await graphqlRequest<{
    stationStatus: ConnectorStatus
  }>(STATION_STATUS, {
    connectorId,
  })

  return data.stationStatus
}
