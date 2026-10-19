import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";

export const PAGE_SIZE = 50;

export function usePagination(items, resetKey = "") {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));

  useEffect(() => {
    setPage(1);
  }, [resetKey]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const pageItems = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return items.slice(start, start + PAGE_SIZE);
  }, [items, page]);

  return { page, setPage, pageItems, totalPages };
}

export function PaginationControls({ page, setPage, totalPages, total, testid = "pagination" }) {
  if (total <= PAGE_SIZE) return null;

  const from = (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3" data-testid={`${testid}-controls`}>
      <span className="text-xs text-muted-foreground" data-testid={`${testid}-summary`}>
        {from}–{to} din {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          data-testid={`${testid}-previous-button`}
          aria-label="Pagina anterioară"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="min-w-20 text-center text-xs font-medium" data-testid={`${testid}-page-indicator`}>
          Pagina {page} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="icon"
          data-testid={`${testid}-next-button`}
          aria-label="Pagina următoare"
          disabled={page >= totalPages}
          onClick={() => setPage(page + 1)}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}