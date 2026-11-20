import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown, Inbox, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  value?: (row: T) => string | number;
  sortable?: boolean;
  align?: "left" | "right";
  className?: string;
}

interface Props<T> {
  data: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  searchKeys?: (row: T) => string;
  searchPlaceholder?: string;
  toolbar?: ReactNode;
  pageSize?: number;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  emptyTitle?: string;
  emptyHint?: string;
  actions?: (row: T) => ReactNode;
}

export function DataTable<T>({
  data,
  columns,
  rowKey,
  searchKeys,
  searchPlaceholder = "Search records…",
  toolbar,
  pageSize = 10,
  loading = false,
  onRowClick,
  emptyTitle = "No records found",
  emptyHint = "Adjust your filters or search terms to see more results.",
  actions,
}: Props<T>) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(null);
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = searchKeys && q ? data.filter((r) => searchKeys(r).toLowerCase().includes(q)) : data;
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col?.value) {
        rows = [...rows].sort((a, b) => {
          const av = col.value!(a);
          const bv = col.value!(b);
          const r = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
          return sort.dir === "asc" ? r : -r;
        });
      }
    }
    return rows;
  }, [data, query, sort, columns, searchKeys]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(page, pages - 1);
  const rows = filtered.slice(current * pageSize, current * pageSize + pageSize);

  return (
    <div className="panel overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-border p-3 sm:flex-row sm:items-center sm:justify-between">
        {searchKeys ? (
          <div className="relative w-full sm:max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
              placeholder={searchPlaceholder}
              className="h-9 pl-8"
            />
          </div>
        ) : (
          <div />
        )}
        <div className="flex flex-wrap items-center gap-2">{toolbar}</div>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/60 hover:bg-secondary/60">
              {columns.map((c) => (
                <TableHead
                  key={c.key}
                  className={cn(
                    "h-10 whitespace-nowrap text-xs font-semibold uppercase tracking-wide text-muted-foreground",
                    c.align === "right" && "text-right",
                    c.className,
                  )}
                >
                  {c.sortable && c.value ? (
                    <button
                      type="button"
                      onClick={() =>
                        setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === "asc" ? "desc" : "asc" } : { key: c.key, dir: "asc" }))
                      }
                      className={cn("inline-flex items-center gap-1 transition-colors hover:text-foreground", c.align === "right" && "flex-row-reverse")}
                    >
                      {c.header}
                      {sort?.key === c.key ? (
                        sort.dir === "asc" ? (
                          <ArrowUp className="size-3" />
                        ) : (
                          <ArrowDown className="size-3" />
                        )
                      ) : (
                        <ChevronsUpDown className="size-3 opacity-40" />
                      )}
                    </button>
                  ) : (
                    c.header
                  )}
                </TableHead>
              ))}
              {actions ? <TableHead className="w-12" /> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {columns.map((c) => (
                      <TableCell key={c.key}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                    {actions ? <TableCell /> : null}
                  </TableRow>
                ))
              : rows.map((row) => (
                  <TableRow
                    key={rowKey(row)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={cn("transition-colors", onRowClick && "cursor-pointer")}
                  >
                    {columns.map((c) => (
                      <TableCell
                        key={c.key}
                        className={cn("py-2.5 text-sm", c.align === "right" && "text-right tabular", c.className)}
                      >
                        {c.render ? c.render(row) : String(c.value?.(row) ?? "")}
                      </TableCell>
                    ))}
                    {actions ? (
                      <TableCell className="py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                        {actions(row)}
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
          </TableBody>
        </Table>
        {!loading && rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
            <div className="rounded-full bg-muted p-3 text-muted-foreground">
              <Inbox className="size-5" />
            </div>
            <p className="text-sm font-medium">{emptyTitle}</p>
            <p className="max-w-sm text-xs text-muted-foreground">{emptyHint}</p>
          </div>
        ) : null}
      </div>

      <div className="flex flex-col gap-2 border-t border-border px-3 py-2.5 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <span>
          {filtered.length === 0 ? 0 : current * pageSize + 1}–{Math.min(filtered.length, (current + 1) * pageSize)} of {filtered.length} records
        </span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={current === 0} onClick={() => setPage(current - 1)}>
            Previous
          </Button>
          <span className="tabular">
            Page {current + 1} / {pages}
          </span>
          <Button variant="outline" size="sm" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
