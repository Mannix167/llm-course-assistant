import { useState, type ComponentProps, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import "katex/dist/katex.min.css";

import { courseImageUrl } from "../api/client";

type ReportViewerProps = {
  markdown: string;
  courseId: number;
  title?: string;
  compactHeader?: boolean;
  onHighlightSelection?: (selectedText: string) => void;
  highlightSaving?: boolean;
  onPageRefClick?: (pageNumber: number) => void;
};

type TocItem = {
  id: string;
  level: number;
  text: string;
};

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), "mark"],
  attributes: {
    ...defaultSchema.attributes,
    mark: [["data-note"], "className", "title"],
    span: [...(defaultSchema.attributes?.span ?? []), "className", "style"],
    div: [...(defaultSchema.attributes?.div ?? []), "className", "style"],
    code: [...(defaultSchema.attributes?.code ?? []), "className"],
  },
};

function resolveImageSrc(courseId: number, src: string | undefined) {
  if (!src) return "";
  const match = src.match(/page_\d{3}\.png/i);
  return match ? courseImageUrl(courseId, match[0]) : src;
}

function textFromChildren(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(textFromChildren).join("");
  if (children && typeof children === "object" && "props" in children) {
    return textFromChildren((children as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

function normalizeLegacyHighlights(markdown: string) {
  return markdown.replace(/==([^=\n]+)==/g, '<mark data-note="highlight">$1</mark>');
}

function stripInlineMarkdown(text: string) {
  return text
    .replace(/<[^>]+>/g, "")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[`*_~>#]/g, "")
    .trim();
}

function headingId(index: number, text: string) {
  const slug = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 36);
  return slug ? `report-heading-${index}-${slug}` : `report-heading-${index}`;
}

function buildHeadingIndex(markdown: string): TocItem[] {
  const items: TocItem[] = [];
  let inFence = false;
  for (const line of markdown.split(/\r?\n/)) {
    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const match = /^(#{1,4})\s+(.+?)\s*$/.exec(line);
    if (!match) continue;
    const text = stripInlineMarkdown(match[2]);
    if (!text) continue;
    items.push({ id: headingId(items.length + 1, text), level: match[1].length, text });
  }
  return items;
}

export function ReportViewer({
  markdown,
  courseId,
  title,
  compactHeader = false,
  onHighlightSelection,
  highlightSaving = false,
  onPageRefClick,
}: ReportViewerProps) {
  const [tocCollapsed, setTocCollapsed] = useState(false);

  if (!markdown.trim()) {
    return <div className="rounded border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500">暂无报告内容</div>;
  }

  const renderedMarkdown = normalizeLegacyHighlights(markdown);
  const tocItems = buildHeadingIndex(renderedMarkdown);
  const showToc = tocItems.length >= 4;
  const showTocPanel = showToc && !tocCollapsed;
  let headingCursor = 0;
  const nextHeading = () => tocItems[headingCursor++];
  const renderPageReferences = (children: ReactNode): ReactNode => {
    if (typeof children === "number") return children;
    if (typeof children !== "string") {
      if (!Array.isArray(children)) return children;
      return children.map((child, index) => <span key={index}>{renderPageReferences(child)}</span>);
    }

    const parts: ReactNode[] = [];
    const pattern = /\u7b2c\s*(\d{1,4})(?:\s*[-~\u2013\u2014\uff0d\u81f3\u5230]\s*(\d{1,4}))?\s*\u9875/g;
    let lastIndex = 0;
    for (const match of children.matchAll(pattern)) {
      const start = Number(match[1]);
      const end = match[2];
      const index = match.index ?? 0;
      if (index > lastIndex) parts.push(children.slice(lastIndex, index));
      parts.push(
        <a
          key={`${index}-${match[0]}`}
          href={`#course-page-${start}`}
          onClick={(event) => {
            event.preventDefault();
            if (Number.isFinite(start)) onPageRefClick?.(start);
          }}
          className="font-medium text-blue-700 underline decoration-blue-300 underline-offset-2 hover:text-blue-900"
        >
          {end ? `第 ${start}-${end} 页` : `第 ${start} 页`}
        </a>,
      );
      lastIndex = index + match[0].length;
    }
    if (lastIndex < children.length) parts.push(children.slice(lastIndex));
    return parts.length ? parts : children;
  };

  return (
    <article className="flex h-full flex-col overflow-hidden rounded border border-zinc-200 bg-white shadow-sm">
      {title ? (
        <div className="flex items-center justify-between border-b border-zinc-200 bg-white px-5 py-3">
          <h3 className="text-sm font-semibold text-zinc-950">{title}</h3>
          <div className="flex items-center gap-2">
            {onHighlightSelection ? (
              <button
                onClick={() => {
                  const selectedText = window.getSelection()?.toString().trim() ?? "";
                  if (selectedText) onHighlightSelection(selectedText);
                }}
                disabled={highlightSaving}
                className="rounded border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60"
              >
                {highlightSaving ? "保存中" : "高亮选中"}
              </button>
            ) : null}
            {showToc ? (
              <button
                onClick={() => setTocCollapsed((value) => !value)}
                className="rounded border border-zinc-200 bg-white px-2.5 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50"
              >
                {tocCollapsed ? "展开目录" : "收起目录"}
              </button>
            ) : null}
            {compactHeader ? <span className="text-xs text-zinc-500">Markdown 讲解内容</span> : null}
          </div>
        </div>
      ) : null}
      <div className={`${compactHeader ? "min-h-0 flex-1 overflow-auto" : ""}`}>
        <div className={`${showTocPanel ? "grid gap-6 p-6 xl:grid-cols-[220px_minmax(0,1fr)]" : "p-6"}`}>
          {showTocPanel ? (
            <aside className="hidden xl:block">
              <nav className="sticky top-4 max-h-[calc(100vh-160px)] overflow-auto border-r border-zinc-200 pr-4 text-sm">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <span className="font-semibold text-zinc-950">报告目录</span>
                  <button
                    onClick={() => setTocCollapsed(true)}
                    className="rounded border border-zinc-200 px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-50"
                  >
                    收起
                  </button>
                </div>
                <div className="space-y-1">
                  {tocItems.map((item) => (
                    <a
                      key={item.id}
                      href={`#${item.id}`}
                      onClick={(event) => {
                        event.preventDefault();
                        document.getElementById(item.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
                      }}
                      className="block rounded px-2 py-1.5 leading-5 text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950"
                      style={{ paddingLeft: `${Math.max(0, item.level - 1) * 12 + 8}px` }}
                    >
                      {item.text}
                    </a>
                  ))}
                </div>
              </nav>
            </aside>
          ) : null}
          <div className="min-w-0">
            {showToc && tocCollapsed ? (
              <button
                onClick={() => setTocCollapsed(false)}
                className="mb-4 rounded border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100"
              >
                展开报告目录
              </button>
            ) : null}
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema], rehypeKatex]}
              components={{
                h1: ({ children }) => {
                  const heading = nextHeading();
                  return <h2 id={heading?.id} className="mb-4 mt-8 scroll-mt-6 border-b border-zinc-200 pb-3 text-2xl font-semibold text-zinc-950 first:mt-0">{children}</h2>;
                },
                h2: ({ children }) => {
                  const heading = nextHeading();
                  return <h3 id={heading?.id} className="mb-3 mt-7 scroll-mt-6 text-xl font-semibold text-zinc-950">{children}</h3>;
                },
                h3: ({ children }) => {
                  const heading = nextHeading();
                  return <h4 id={heading?.id} className="mb-2 mt-5 scroll-mt-6 text-base font-semibold text-zinc-900">{children}</h4>;
                },
                h4: ({ children }) => {
                  const heading = nextHeading();
                  return <h5 id={heading?.id} className="mb-2 mt-5 scroll-mt-6 text-sm font-semibold text-zinc-900">{children}</h5>;
                },
                p: ({ children }) => <p className="mb-4 leading-7 text-zinc-800">{renderPageReferences(children)}</p>,
                strong: ({ children }) => <strong className="font-semibold text-zinc-900">{renderPageReferences(children)}</strong>,
                em: ({ children }) => <em>{renderPageReferences(children)}</em>,
                ul: ({ children }) => <ul className="mb-5 list-disc space-y-2 pl-6 text-zinc-800">{children}</ul>,
                ol: ({ children }) => <ol className="mb-5 list-decimal space-y-2 pl-6 text-zinc-800">{children}</ol>,
                li: ({ children }) => <li className="leading-7">{renderPageReferences(children)}</li>,
                blockquote: ({ children }) => <blockquote className="mb-4 border-l-4 border-zinc-300 bg-zinc-50 px-4 py-3 text-sm leading-7 text-zinc-700">{children}</blockquote>,
                hr: () => <hr className="my-8 border-zinc-200" />,
                a: ({ href, children }) => (
                  <a
                    href={href}
                    target={href?.startsWith("#course-page-") ? undefined : "_blank"}
                    rel={href?.startsWith("#course-page-") ? undefined : "noreferrer"}
                    onClick={(event) => {
                      if (!href?.startsWith("#course-page-")) return;
                      event.preventDefault();
                      const pageNumber = Number(href.replace("#course-page-", ""));
                      if (Number.isFinite(pageNumber)) onPageRefClick?.(pageNumber);
                    }}
                    className="font-medium text-blue-700 underline decoration-blue-300 underline-offset-2 hover:text-blue-900"
                  >
                    {children}
                  </a>
                ),
                img: ({ src, alt }) => (
                  <figure className="my-6 overflow-hidden rounded border border-zinc-200 bg-zinc-50">
                    <img src={resolveImageSrc(courseId, src)} alt={alt || "课件截图"} className="mx-auto max-h-[540px] w-full object-contain" loading="lazy" />
                    {alt ? <figcaption className="border-t border-zinc-200 px-3 py-2 text-sm text-zinc-500">{alt}</figcaption> : null}
                  </figure>
                ),
                table: ({ children }) => (
                  <div className="mb-6 overflow-x-auto rounded border border-zinc-200">
                    <table className="min-w-full divide-y divide-zinc-200 text-sm">{children}</table>
                  </div>
                ),
                thead: ({ children }) => <thead className="bg-zinc-50">{children}</thead>,
                tbody: ({ children }) => <tbody className="divide-y divide-zinc-100 bg-white">{children}</tbody>,
                th: ({ children }) => <th className="px-3 py-2 text-left font-semibold text-zinc-700">{renderPageReferences(children)}</th>,
                td: ({ children }) => <td className="px-3 py-2 align-top leading-6 text-zinc-700">{renderPageReferences(children)}</td>,
                pre: ({ children }) => <pre className="mb-6 overflow-x-auto rounded border border-zinc-200 bg-zinc-950 p-4 text-sm leading-6 text-zinc-100">{children}</pre>,
                code: ({ className, children, ...props }: ComponentProps<"code">) => {
                  const inline = !className;
                  return (
                    <code className={inline ? "rounded bg-zinc-100 px-1 py-0.5 text-[0.92em] text-zinc-800" : `${className ?? ""} text-zinc-100`} {...props}>
                      {children}
                    </code>
                  );
                },
                mark: ({ children }) => (
                  <mark
                    onClick={(event) => {
                      event.stopPropagation();
                      onHighlightSelection?.(textFromChildren(children));
                    }}
                    className="cursor-pointer rounded bg-amber-200/80 px-1 text-zinc-950 ring-1 ring-amber-300/70"
                    title="点击取消高亮"
                  >
                    {children}
                  </mark>
                ),
              }}
            >
              {renderedMarkdown}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </article>
  );
}
