"use client";

import { useRef, useState } from "react";
import { useResolveIssueMutation } from "@/queries/index";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Camera, Loader2, X } from "lucide-react";
import { toast } from "sonner";

/**
 * Engineer "after photo" capture for POST /resolution.
 *
 * The backend closes the issue and stores the upload as after-fix evidence, so
 * the photo is required and the notes are optional context.
 */
export function ResolveDialog({
  issueId,
  open,
  onOpenChange,
}: {
  issueId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const resolveMutation = useResolveIssueMutation();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Selecting/replacing a file swaps the object URL. Done here rather than in an
  // effect so we never setState synchronously during render/effects.
  function selectFile(next: File | null) {
    if (preview) URL.revokeObjectURL(preview);
    setPreview(next ? URL.createObjectURL(next) : null);
    setFile(next);
    if (!next && inputRef.current) inputRef.current.value = "";
  }

  // Reset the draft whenever the dialog closes, however it was closed
  // (submit, Cancel, Escape, or clicking the overlay).
  function handleOpenChange(next: boolean) {
    if (!next) {
      if (preview) URL.revokeObjectURL(preview);
      setPreview(null);
      setFile(null);
      setNotes("");
      if (inputRef.current) inputRef.current.value = "";
    }
    onOpenChange(next);
  }

  async function handleSubmit() {
    if (!file) {
      toast.error("Attach a photo of the completed work.");
      return;
    }
    try {
      await resolveMutation.mutateAsync({ issueId, file, notes });
      toast.success("Issue resolved with photo evidence");
      handleOpenChange(false);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to resolve issue");
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Resolve issue</DialogTitle>
          <DialogDescription>
            Attach a photo of the completed work. It is stored as after-fix evidence.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label className="mb-1.5 block">Photo proof</Label>
            {preview ? (
              <div className="relative overflow-hidden rounded-lg border">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={preview}
                  alt="Resolution preview"
                  className="h-44 w-full object-cover"
                />
                <button
                  type="button"
                  onClick={() => selectFile(null)}
                  className="absolute right-2 top-2 rounded-full bg-background/90 p-1.5 text-muted-foreground shadow-sm transition-colors hover:text-foreground"
                  aria-label="Remove photo"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="flex h-32 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-muted/30 text-muted-foreground transition-colors hover:bg-muted/60"
              >
                <Camera className="h-6 w-6" />
                <span className="text-sm font-medium">Upload after photo</span>
                <span className="text-xs">JPG or PNG</span>
              </button>
            )}
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => selectFile(e.target.files?.[0] ?? null)}
            />
          </div>

          <div>
            <Label htmlFor="resolution-notes" className="mb-1.5 block">
              Notes (optional)
            </Label>
            <Textarea
              id="resolution-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="What was done to fix this?"
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={resolveMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!file || resolveMutation.isPending}
            className="gap-2"
          >
            {resolveMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Mark resolved
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
