import { useState } from "react";
import { Bot, ChevronDown, Loader2, Send, ShieldCheck, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader, SectionCard } from "@/components/page-parts";
import { useAskAssistant, useAssistantStatus } from "@/hooks/useApi";
import { usePageMeta } from "@/hooks/use-page-meta";
import type { AssistantAnswer } from "@/types/domain";

const SUGGESTIONS = [
  "Which month consumed the most electricity, and what was each facility's consumption that month?",
  "Which facilities have not yet submitted activity data for 2026-07?",
  "Which reporting periods are open, in review and locked?",
  "List all emission factors.",
  "Are we on track for our emission reduction targets?",
  "What does the forecast say about the next 12 months?",
];

interface Turn { q: string; a?: AssistantAnswer; error?: string }

export default function AssistantPage() {
  usePageMeta("AI Assistant — CarbonOps AI", "Ask questions about your emissions data. A local open-weight model answers using only the platform's calculated figures.");
  const { data: status } = useAssistantStatus();
  const ask = useAskAssistant();
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const ready = !!status?.reachable && status.modelInstalled;

  const send = async (text: string) => {
    const question = text.trim();
    if (question.length < 3 || ask.isPending) return;
    setQ("");
    setTurns((t) => [{ q: question }, ...t]);
    try {
      const a = await ask.mutateAsync(question);
      setTurns((t) => t.map((x, i) => (i === 0 ? { ...x, a } : x)));
    } catch (e) {
      setTurns((t) => t.map((x, i) => (i === 0 ? { ...x, error: e instanceof Error ? e.message : "Request failed" } : x)));
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader breadcrumb="Governance" title="AI Assistant"
        description="Ask about emissions, targets, forecasts, initiatives and alerts. A local open-weight model (via Ollama) picks the platform's own calculations as tools and words the result — every figure it quotes must appear in the tool output or the answer is withheld." />

      <div className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${ready ? "border-emerald-300/60 bg-emerald-50 dark:bg-emerald-950/30" : "border-amber-300/60 bg-amber-50 dark:bg-amber-950/30"}`}>
        {ready ? <ShieldCheck className="mt-0.5 size-4 text-emerald-700" /> : <TriangleAlert className="mt-0.5 size-4 text-amber-700" />}
        <div>
          <p className="font-medium">{ready ? `Local model ready: ${status?.model}` : "Local model not ready"}</p>
          <p className="text-muted-foreground">
            {ready ? "Runs on this server through Ollama; no data leaves your network." : (status?.message ?? "Checking…")}
          </p>
          {!ready && (
            <p className="mt-1 text-xs text-muted-foreground">
              Setup (free): install Ollama (MIT licence) → <code>ollama pull {status?.model ?? "qwen2.5:7b"}</code> (Apache-2.0 model) → leave <code>ollama serve</code> running.
            </p>
          )}
        </div>
      </div>

      <SectionCard title="Ask a question">
        <div className="space-y-3">
          <Textarea aria-label="Question" rows={2} maxLength={500} value={q} placeholder="e.g. Which facility had the highest Scope 1 emissions in 2026-05?"
            onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void send(q); }} />
          <div className="flex flex-wrap items-center gap-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-muted" onClick={() => void send(s)}>{s}</button>
            ))}
            <Button className="ml-auto" onClick={() => void send(q)} disabled={ask.isPending || q.trim().length < 3}>
              {ask.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} Ask
            </Button>
          </div>
        </div>
      </SectionCard>

      {turns.map((t, i) => (
        <SectionCard key={`${i}-${t.q}`} title={t.q}>
          {!t.a && !t.error && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Calling tools and waiting for the local model… (the first answer can take a minute while the model loads)</p>}
          {t.error && <p className="text-sm text-destructive">{t.error}</p>}
          {t.a && (<div className="space-y-3">
            {t.a.mode === "answered" && <p className="flex gap-2 text-sm"><Bot className="mt-0.5 size-4 shrink-0 text-primary" /> <span className="whitespace-pre-wrap">{t.a.answer}</span></p>}
            {t.a.mode !== "answered" && (
              <p className="rounded-md border border-amber-300/60 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                {t.a.message}{t.a.ungrounded.length ? ` Unsupported figures: ${t.a.ungrounded.join(", ")}.` : ""}
                {t.a.rawAnswer ? <span className="mt-2 block text-xs"><strong>Model's withheld reply (for diagnosis):</strong> {t.a.rawAnswer}</span> : null}
              </p>
            )}
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Data used ({t.a.toolCalls.length} tool call{t.a.toolCalls.length === 1 ? "" : "s"}) · model {t.a.model}</p>
              {t.a.toolCalls.length === 0 && <p className="text-xs text-muted-foreground">No platform data was retrieved.</p>}
              {t.a.toolCalls.map((c, k) => (
                <details key={k} className="group mb-1 rounded-md border">
                  <summary className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm">
                    <ChevronDown className="size-4 transition-transform group-open:rotate-180" />
                    <code>{c.name}</code><span className="text-xs text-muted-foreground">{Object.keys(c.arguments).length ? JSON.stringify(c.arguments) : ""}</span>
                  </summary>
                  <pre className="max-h-72 overflow-auto border-t bg-muted/40 p-3 text-xs">{JSON.stringify(c.result, null, 2)}</pre>
                </details>
              ))}
            </div>
          </div>)}
        </SectionCard>
      ))}
    </div>
  );
}
