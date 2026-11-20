/** Which review states count toward totals and charts.
 *  "approved": only Approved records (the reportable inventory). "pending": also records awaiting a decision.
 *  Rejected and Draft records are never counted — they stay in the ledger for traceability only. */
export type Basis = "approved" | "pending";

export const countsToward = (status: string, basis: Basis): boolean =>
  status === "Approved" || (basis === "pending" && (status === "Under Review" || status === "Submitted"));

export const BASIS_LABEL: Record<Basis, string> = {
  approved: "Approved only",
  pending: "Approved + pending review",
};
