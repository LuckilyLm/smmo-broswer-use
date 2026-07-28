import { AlertCircle, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  title: string;
  description?: string;
  compact?: boolean;
  className?: string;
}

export function EmptyState({ title, description, compact = false, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-4 text-center text-muted-foreground", compact ? "min-h-32 py-6" : "min-h-48 py-10", className)}>
      <Inbox className="mb-3 h-8 w-8 text-border" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && <p className="mt-1 max-w-md text-xs leading-relaxed">{description}</p>}
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  description: string;
  onRetry?: () => void;
}

export function ErrorState({ title = "加载失败", description, onRetry }: ErrorStateProps) {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center px-4 text-center">
      <AlertCircle className="mb-3 h-8 w-8 text-destructive" />
      <p className="text-sm font-semibold text-foreground">{title}</p>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
      {onRetry && <Button className="mt-4" variant="outline" onClick={onRetry}>重试</Button>}
    </div>
  );
}
