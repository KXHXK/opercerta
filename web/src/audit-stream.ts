import { raiseApiError } from "./api/client";

export type AuditEvent = {
  sequence: number;
  type: string;
  data: Record<string, unknown>;
};

function parseSnapshot(body: string, afterSequence: number): AuditEvent[] {
  const events = new Map<number, AuditEvent>();

  for (const block of body.split(/\r?\n\r?\n/)) {
    const fields = new Map<string, string>();
    for (const line of block.split(/\r?\n/)) {
      const separator = line.indexOf(":");
      if (separator > 0) {
        fields.set(line.slice(0, separator), line.slice(separator + 1).trimStart());
      }
    }

    const sequence = Number(fields.get("id"));
    const type = fields.get("event");
    const data = fields.get("data");
    if (!Number.isSafeInteger(sequence) || sequence <= afterSequence || !type || !data) {
      continue;
    }

    try {
      const parsed = JSON.parse(data) as unknown;
      if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
        events.set(sequence, { sequence, type, data: parsed as Record<string, unknown> });
      }
    } catch {
      // A malformed snapshot event is ignored; later valid events still render.
    }
  }

  return [...events.values()].sort((left, right) => left.sequence - right.sequence);
}

export async function readAuditSnapshot(
  operationId: string,
  afterSequence: number,
  authorization: string
): Promise<AuditEvent[]> {
  const request = {
    headers: {
      Authorization: authorization,
      ...(afterSequence > 0 ? { "Last-Event-ID": String(afterSequence) } : {})
    }
  };

  for (let attempt = 0; attempt <= 3; attempt += 1) {
    try {
      const response = await fetch(`/api/v1/operations/${operationId}/events`, request);
      if (!response.ok) {
        await raiseApiError(response);
      }

      return parseSnapshot(await response.text(), afterSequence);
    } catch (error) {
      if (!(error instanceof TypeError) || attempt === 3) {
        throw error;
      }
    }
  }

  throw new Error("audit_snapshot_unavailable");
}
