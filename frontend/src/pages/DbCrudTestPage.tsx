import { useState } from "react";

import { usePageMeta } from "@/hooks/use-page-meta";
import { adminToolsApi } from "@/services/entities";

export default function DbCrudTestPage() {
  usePageMeta("MongoDB CRUD test — CarbonOps AI");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [seedResult, setSeedResult] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [seedLoading, setSeedLoading] = useState(false);

  const runFacilityCrudTest = adminToolsApi.crudTest;
  const runSeed = adminToolsApi.seedFacilities;

  const handleCrudTest = async () => {
    setLoading(true);
    setResult(null);

    try {
      const response = await runFacilityCrudTest();
      setResult(response);
    } catch (error) {
      console.error("CRUD TEST ERROR:", error);

      setResult({
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSeed = async () => {
    setSeedLoading(true);
    setSeedResult(null);

    try {
      const response = await runSeed();
      setSeedResult(response);
    } catch (error) {
      console.error("SEED ERROR:", error);

      setSeedResult({
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSeedLoading(false);
    }
  };

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">
          MongoDB Facility Database Test
        </h1>

        <p className="mt-2 text-sm text-muted-foreground">
          Temporary page for testing MongoDB connectivity, CRUD operations,
          and facility seeding.
        </p>
      </div>

      {/* CRUD TEST */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">
          Facility CRUD Test
        </h2>

        <button
          type="button"
          onClick={handleCrudTest}
          disabled={loading}
          className="cursor-pointer rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
        >
          {loading ? "Running test..." : "Run CRUD Test"}
        </button>

        {result && (
          <pre className="overflow-auto rounded-lg border bg-muted p-4 text-sm">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </section>

      {/* SEED TEST */}
      <section className="space-y-3 border-t pt-6">
        <h2 className="text-lg font-semibold">
          Seed Facilities
        </h2>

        <button
          type="button"
          onClick={handleSeed}
          disabled={seedLoading}
          className="cursor-pointer rounded-md border px-4 py-2 disabled:opacity-50"
        >
          {seedLoading ? "Seeding..." : "Seed Facilities"}
        </button>

        {seedResult != null && (
          <pre className="overflow-auto rounded-lg border bg-muted p-4 text-sm">
            {JSON.stringify(seedResult, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}