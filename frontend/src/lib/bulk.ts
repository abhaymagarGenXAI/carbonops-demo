import { toast } from "sonner";

/** Runs one request per id (sequentially, so one failure never hides the others) and reports a single summary toast. */
export async function runBulk(ids: string[], verb: string, fn: (id: string) => Promise<unknown>): Promise<{ done: string[]; failed: { id: string; reason: string }[] }> {
  const done: string[] = [];
  const failed: { id: string; reason: string }[] = [];
  for (const id of ids) {
    try {
      await fn(id);
      done.push(id);
    } catch (e) {
      failed.push({ id, reason: e instanceof Error ? e.message : "Unexpected error" });
    }
  }
  if (failed.length === 0) toast.success(`${done.length} ${verb}`);
  else toast.error(`${done.length} ${verb}, ${failed.length} failed`, { description: failed.slice(0, 3).map((f) => `${f.id}: ${f.reason}`).join(" · ") + (failed.length > 3 ? " …" : "") });
  return { done, failed };
}
