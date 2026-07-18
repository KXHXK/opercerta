import { expect, it, vi } from "vitest";

import { readAuditSnapshot } from "./audit-stream";

it("deduplicates replayed SSE sequences and carries authorization", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(
      "id: 3\nevent: approval_requested\ndata: {\"request\":\"approved\"}\n\nid: 3\nevent: approval_requested\ndata: {}\n\nid: 4\nevent: operation_completed\ndata: {}\n\n",
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );
  vi.stubGlobal("fetch", fetchMock);

  const events = await readAuditSnapshot("operation-1", 2, "Bearer memory-only");

  expect(events.map((event) => event.sequence)).toEqual([3, 4]);
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/operations/operation-1/events", {
    headers: { Authorization: "Bearer memory-only", "Last-Event-ID": "2" }
  });
});

it("reconnects a broken snapshot up to three times", async () => {
  const fetchMock = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("network error"))
    .mockRejectedValueOnce(new TypeError("network error"))
    .mockRejectedValueOnce(new TypeError("network error"))
    .mockResolvedValueOnce(
      new Response("id: 5\nevent: operation_completed\ndata: {}\n\n", { status: 200 })
    );
  vi.stubGlobal("fetch", fetchMock);

  const events = await readAuditSnapshot("operation-1", 4, "Bearer memory-only");

  expect(events.map((event) => event.sequence)).toEqual([5]);
  expect(fetchMock).toHaveBeenCalledTimes(4);
});
