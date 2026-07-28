import { AlertTriangle, CheckCircle, Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type SaveState = "idle" | "saving" | "success" | "error";

interface StickySaveBarProps {
  dirty: boolean;
  state: SaveState;
  onCancel: () => void;
  onSave: () => void;
  className?: string;
}

export default function StickySaveBar({ dirty, state, onCancel, onSave, className }: StickySaveBarProps) {
  if (!dirty && state !== "success") return null;

  return (
    <div
      data-testid="sticky-save-bar"
      className={cn(
        "sticky bottom-0 z-20 mt-8 flex min-h-16 items-center gap-3 border-t bg-card/95 px-4 py-3 backdrop-blur supports-[padding:max(0px)]:pb-[max(12px,env(safe-area-inset-bottom))] md:px-6",
        className,
      )}
    >
      <div className="min-w-0 text-sm">
        {state === "error" && <span className="flex items-center gap-1.5 text-destructive"><AlertTriangle className="h-4 w-4" />保存失败，输入内容已保留</span>}
        {state === "success" && <span className="flex items-center gap-1.5 text-emerald-700"><CheckCircle className="h-4 w-4" />设置已保存</span>}
        {state === "idle" && dirty && <span className="text-muted-foreground">有未保存的更改</span>}
        {state === "saving" && <span className="text-muted-foreground">正在保存更改…</span>}
      </div>
      <div className="ml-auto flex shrink-0 gap-2">
        <Button variant="outline" size="lg" onClick={onCancel} disabled={state === "saving"}>取消</Button>
        <Button size="lg" onClick={onSave} disabled={!dirty || state === "saving"}>
          {state === "saving" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {state === "saving" ? "保存中…" : "保存修改"}
        </Button>
      </div>
    </div>
  );
}
