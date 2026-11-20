import { useQuery } from "@tanstack/react-query";

import { usePageMeta } from "@/hooks/use-page-meta";
import { adminToolsApi } from "@/services/entities";

export default function DbModelTestPage() {
  usePageMeta("MongoDB model test — CarbonOps AI");
  const { data, error, isLoading } = useQuery({
    queryKey: ["admin", "db-status"],
    queryFn: adminToolsApi.status,
    retry: false,
  });

  return (
    <div className="space-y-4 p-8">
      <h1 className="text-2xl font-semibold">MongoDB Model Test</h1>

      <pre className="rounded-lg border p-4">
        {isLoading ? "Checking…" : JSON.stringify(error ? { error: error.message } : data, null, 2)}
      </pre>
    </div>
  );
}
