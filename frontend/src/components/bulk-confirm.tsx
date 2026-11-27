import { useState } from "react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  /** Show a comment box; `requireComment` makes it mandatory (e.g. rejections). */
  comment?: boolean;
  requireComment?: boolean;
  onCancel: () => void;
  onConfirm: (comment: string) => Promise<void> | void;
}

/** One confirmation step for every multi-select action (delete, approve, reject …). */
export function BulkConfirm({ open, title, description, confirmLabel, comment, requireComment, onCancel, onConfirm }: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const blocked = busy || (!!requireComment && !text.trim());
  return (
    <AlertDialog open={open} onOpenChange={(o) => !o && !busy && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {comment ? <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={requireComment ? "Reason (required)" : "Comment (optional)"} aria-label="Comment" /> : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={blocked}
            onClick={async (e) => {
              e.preventDefault();
              setBusy(true);
              try { await onConfirm(text.trim()); setText(""); } finally { setBusy(false); }
            }}
          >
            {busy ? "Working…" : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
