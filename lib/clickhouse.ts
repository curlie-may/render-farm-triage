import { createClient, type ClickHouseClient } from "@clickhouse/client";

let client: ClickHouseClient | null = null;

/** Lazily-constructed singleton ClickHouse client. Server-side only — never
 * import this from client components. Credentials come from CLICKHOUSE_*
 * env vars, which must not be exposed to the browser. */
export function getClient(): ClickHouseClient {
  if (client) return client;

  const host = process.env.CLICKHOUSE_HOST;
  const username = process.env.CLICKHOUSE_USER;
  const password = process.env.CLICKHOUSE_PASSWORD;
  const database = process.env.CLICKHOUSE_DATABASE;

  if (!host || !username || !password || !database) {
    throw new Error(
      "Missing CLICKHOUSE_HOST / CLICKHOUSE_USER / CLICKHOUSE_PASSWORD / CLICKHOUSE_DATABASE env vars"
    );
  }

  const url = host.startsWith("http") ? host : `https://${host}:8443`;

  client = createClient({ url, username, password, database });
  return client;
}

/** Runs a parameterized query and returns rows as JSON objects. */
export async function queryRows<T = Record<string, unknown>>(
  query: string,
  query_params?: Record<string, unknown>
): Promise<T[]> {
  const result = await getClient().query({
    query,
    query_params,
    format: "JSONEachRow",
  });
  return result.json<T>();
}
