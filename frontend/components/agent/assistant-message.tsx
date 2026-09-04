"use client";

import React, { useCallback, useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import { Dot } from "@/components/primitives";
import { MarkdownRenderer } from "./markdown-renderer";

function StreamingIndicator() {
  return (
    <span
      className="ml-1 inline-flex h-1.5 w-1.5 rounded-full bg-accent anim-blink"
      aria-label="Agent is responding"
      role="status"
    />
  );
}

export function AssistantMessage({
  message,
  model,
  isStreaming,
  className,
}: {
  message: string;
  model?: string;
  isStreaming?: boolean;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    if (!message) return;
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
    }
  }, [message]);

  return (
    <div
      className={cn(
        "group relative max-w-full rounded rounded-tl-none border border-hairline bg-canvas-panel/60",
        className
      )}
    >
      <div className="p-2.5">
        <MarkdownRenderer content={message} isStreaming={isStreaming} />
        {isStreaming && <StreamingIndicator />}
      </div>
      <div className="flex items-center justify-between border-t border-hairline px-2.5 py-1.5">
        <div className="flex items-center gap-2 text-[9px] text-muted">
          {model && <span>via {model}</span>}
          {isStreaming && (
            <span className="flex items-center gap-1 text-accent">
              <Dot tone="accent" pulse className="h-1.5 w-1.5" />
              streaming
            </span>
          )}
        </div>
        <button
          onClick={handleCopy}
          aria-label={copied ? "Copied" : "Copy response"}
          title={copied ? "Copied" : "Copy response"}
          className={cn(
            "flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-muted transition-colors hover:bg-canvas-subtle hover:text-accent",
            copied && "text-success"
          )}
        >
          {copied ? (
            <Check className="h-3 w-3" strokeWidth={1.5} />
          ) : (
            <Copy className="h-3 w-3" strokeWidth={1.5} />
          )}
          {copied ? "copied" : "copy"}
        </button>
      </div>
    </div>
  );
}
