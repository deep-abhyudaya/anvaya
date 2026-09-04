"use client";

import React, { useCallback, useMemo, useState } from "react";
import ReactMarkdown, { type Components, type ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { Check, Copy } from "lucide-react";
import type { Element } from "hast";
import { cn } from "@/lib/utils";
import { highlightCode } from "@/lib/shiki";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getCodeBlockContent(node: Element): { code: string; lang?: string } {
  const codeNode = node.children.find(
    (c): c is Element =>
      c.type === "element" && (c as Element).tagName === "code"
  );

  const classNameProp = codeNode?.properties?.className;
  const rawClass = Array.isArray(classNameProp)
    ? (classNameProp as string[]).join(" ")
    : typeof classNameProp === "string"
      ? classNameProp
      : "";

  const lang = rawClass.match(/language-(\S+)/)?.[1];

  const code = codeNode
    ? (codeNode.children as any[])
        .map((c) => (c.type === "text" ? (c.value as string) : ""))
        .join("")
    : "";

  return {
    code,
    lang,
  };
}

function MarkdownInlineCode({
  className,
  children,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  node,
  ...props
}: React.JSX.IntrinsicElements["code"] & ExtraProps) {
  return (
    <code
      className={cn(
        "rounded border border-hairline bg-canvas-subtle px-1 py-0.5 font-mono text-[12px] text-accent",
        className
      )}
      {...props}
    >
      {children}
    </code>
  );
}

function MarkdownCodeBlock({
  code,
  lang,
  isStreaming,
}: {
  code: string;
  lang?: string;
  isStreaming: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const displayed = code.replace(/\n$/, "");
  const label = lang || "text";

  const fallback = `<code class="font-mono text-[12px] text-secondary">${escapeHtml(displayed)}</code>`;
  const html = useMemo(() => {
    if (isStreaming || !lang) return fallback;
    return highlightCode(displayed, lang) || fallback;
  }, [displayed, lang, isStreaming, fallback]);

  const handleCopy = useCallback(() => {
    if (!displayed) return;
    navigator.clipboard.writeText(displayed).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  }, [displayed]);

  return (
    <div className="group/my-code relative my-2 overflow-hidden rounded border border-hairline bg-canvas-elevated">
      <div className="flex items-center justify-between border-b border-hairline bg-canvas-subtle/60 px-2.5 py-1.5">
        <span className="font-mono text-[10px] uppercase tracking-wider text-accent">
          {label}
        </span>
        <button
          onClick={handleCopy}
          aria-label={copied ? "Copied" : "Copy code"}
          title={copied ? "Copied" : "Copy code"}
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
      <div
        className="shiki-pre overflow-x-auto whitespace-pre p-3 font-mono text-[12px] leading-relaxed"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}

function MarkdownLink({
  href,
  children,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  node,
  ...props
}: React.JSX.IntrinsicElements["a"] & ExtraProps) {
  if (!href) {
    return <span className="text-secondary">{children}</span>;
  }
  const isExternal =
    typeof href === "string" && /^https?:\/\//.test(href) && !href.startsWith("/");
  return (
    <a
      href={href}
      className="break-all text-accent underline underline-offset-2 transition-colors hover:text-accent/80"
      target={isExternal ? "_blank" : undefined}
      rel={isExternal ? "noopener noreferrer" : undefined}
      {...props}
    >
      {children}
    </a>
  );
}

function MarkdownTable({ children }: React.JSX.IntrinsicElements["table"]) {
  return (
    <div className="my-2 w-full overflow-x-auto">
      <table className="w-full border-collapse text-left text-[12px] text-secondary">
        {children}
      </table>
    </div>
  );
}

function MarkdownTaskInput({
  checked,
  disabled,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  node,
  ...props
}: React.JSX.IntrinsicElements["input"] & ExtraProps) {
  return (
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      className="h-3 w-3 accent-accent"
      {...props}
    />
  );
}

function createMarkdownComponents(isStreaming: boolean): Components {
  return {
    a: MarkdownLink,
    blockquote: ({ children }) => (
      <blockquote className="my-2 border-l-2 border-accent/40 bg-canvas-subtle/30 py-1 pl-3 italic text-secondary">
        {children}
      </blockquote>
    ),
    code: MarkdownInlineCode,
    del: ({ children }) => (
      <del className="text-muted line-through">{children}</del>
    ),
    em: ({ children }) => <em className="italic text-secondary">{children}</em>,
    h1: ({ children }) => (
      <h1 className="mb-2 mt-4 border-b border-hairline pb-1 font-mono text-[14px] font-semibold uppercase tracking-wider text-accent">
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className="mb-1.5 mt-3 font-mono text-[13px] font-semibold uppercase tracking-wider text-primary">
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="mb-1 mt-2 font-mono text-[12px] font-medium uppercase tracking-wider text-secondary">
        {children}
      </h3>
    ),
    h4: ({ children }) => (
      <h4 className="mb-1 mt-2 font-mono text-[12px] font-medium text-secondary">
        {children}
      </h4>
    ),
    h5: ({ children }) => (
      <h5 className="mb-1 mt-2 font-mono text-[11px] font-medium text-secondary">
        {children}
      </h5>
    ),
    h6: ({ children }) => (
      <h6 className="mb-1 mt-2 font-mono text-[11px] font-medium text-secondary">
        {children}
      </h6>
    ),
    hr: () => <hr className="my-3 border-hairline" />,
    img: ({ src, alt, title }) => (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={alt}
        title={title}
        className="my-2 max-h-48 max-w-full rounded border border-hairline object-contain"
      />
    ),
    input: MarkdownTaskInput,
    li: ({ children, className }) => (
      <li
        className={cn(
          "my-0.5 break-words",
          typeof className === "string" &&
            className.includes("task-list-item") &&
            "flex items-center gap-2"
        )}
      >
        {children}
      </li>
    ),
    ol: ({ children, className }) => (
      <ol
        className={cn(
          "my-2 list-decimal space-y-0.5 pl-5",
          typeof className === "string" &&
            className.includes("contains-task-list") &&
            "list-none pl-0"
        )}
      >
        {children}
      </ol>
    ),
    p: ({ children }) => (
      <p className="my-2 max-w-prose break-words text-[13px] leading-relaxed text-secondary">
        {children}
      </p>
    ),
    pre: ({ node }) => {
      if (!node) return null;
      const { code, lang } = getCodeBlockContent(node as Element);
      if (!code) return null;
      return <MarkdownCodeBlock code={code} lang={lang} isStreaming={isStreaming} />;
    },
    strong: ({ children }) => (
      <strong className="font-semibold text-primary">{children}</strong>
    ),
    table: MarkdownTable,
    tbody: ({ children }) => <tbody>{children}</tbody>,
    td: ({ children }) => (
      <td className="border-b border-hairline px-2 py-1.5 break-words">
        {children}
      </td>
    ),
    th: ({ children }) => (
      <th className="border-b border-hairline bg-canvas-subtle/40 px-2 py-1.5 text-left font-medium text-primary">
        {children}
      </th>
    ),
    thead: ({ children }) => (
      <thead className="border-b border-hairline">{children}</thead>
    ),
    tr: ({ children }) => <tr className="last:border-0">{children}</tr>,
    ul: ({ children, className }) => (
      <ul
        className={cn(
          "my-2 list-disc space-y-0.5 pl-5",
          typeof className === "string" &&
            className.includes("contains-task-list") &&
            "list-none pl-0"
        )}
      >
        {children}
      </ul>
    ),
  };
}

class MarkdownErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback: string },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode; fallback: string }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Markdown render error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <pre className="whitespace-pre-wrap rounded border border-critical/30 bg-critical-dim/10 p-2.5 font-mono text-[12px] text-critical">
          {this.props.fallback}
        </pre>
      );
    }
    return this.props.children;
  }
}

function MarkdownRendererInternal({
  content,
  isStreaming,
  className,
}: {
  content: string;
  isStreaming?: boolean;
  className?: string;
}) {
  const streaming = Boolean(isStreaming);
  const components = useMemo(
    () => createMarkdownComponents(streaming),
    [streaming]
  );

  if (!content) {
    return null;
  }

  return (
    <MarkdownErrorBoundary fallback={content}>
      <div
        className={cn(
          "markdown-prose min-w-0 text-[13px] leading-relaxed",
          className
        )}
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeSanitize]}
          components={components}
        >
          {content}
        </ReactMarkdown>
      </div>
    </MarkdownErrorBoundary>
  );
}

const MarkdownRenderer = React.memo(
  MarkdownRendererInternal,
  (prev, next) =>
    prev.content === next.content &&
    prev.isStreaming === next.isStreaming &&
    prev.className === next.className
);

export { MarkdownRenderer, MarkdownCodeBlock, MarkdownInlineCode };
