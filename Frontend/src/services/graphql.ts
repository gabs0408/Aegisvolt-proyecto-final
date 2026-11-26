
interface GraphQLResponse<T> {
  data?: T
  errors?: {
    message: string
  }[]
}

export async function graphqlRequest<T>(
  query: string,
  variables: Record<string, unknown> = {},
): Promise<T> {
  const response = await fetch('/graphql', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      variables,
    }),
  })

  if (!response.ok) {
    throw new Error(
      `Error de conexión: ${response.status}`,
    )
  }

  const result: GraphQLResponse<T> =
    await response.json()

  if (result.errors?.length) {
    throw new Error(
      result.errors.map(error => error.message).join(', '),
    )
  }

  if (!result.data) {
    throw new Error('El servidor no devolvió datos')
  }

  return result.data
}
