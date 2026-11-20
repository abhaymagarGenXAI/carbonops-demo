import type { AiAlert } from "@/types/domain";

/** Where an alert should take the current role. Reviewers act in Approvals, data owners in Activity Data. */
export function alertLink(a: Pick<AiAlert, "kind">, role: string): string {
  const reviewer = role === "Sustainability Manager";
  if (a.kind === "inspection") return "/assets";
  return reviewer ? "/approvals" : "/activity";
}

export const alertLinkLabel = (to: string) => (to === "/approvals" ? "Open Approvals" : to === "/assets" ? "Open Assets" : "Open Activity Data");
