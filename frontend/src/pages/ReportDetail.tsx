import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  GitCompare,
  GripVertical,
  ListTree,
  MessageSquareText,
  RefreshCw,
  Square,
  Trash2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";

import {
  courseImageUrl,
  deleteReport,
  getReport,
  listReportSteps,
  reportMarkdownDownloadUrl,
  reportPdfDownloadUrl,
  stopReportGeneration,
  updateReportMarkdown,
} from "../api/client";
import { ChatBox } from "../components/ChatBox";
import { FeedbackBox } from "../components/FeedbackBox";
import { ReportViewer } from "../components/ReportViewer";
import { StepOutputPanel } from "../components/StepOutputPanel";
import type { Course, GenerationStep, ReportDetail as ReportDetailType } from "../types";

type ReportDetailProps = {
  reportId: number | null;
  course: Course | null;
  onReportChanged?: (preferredReportId?: number | null) => void;
};

type TabKey = "report" | "outline" | "summary" | "steps" | "chat" | "feedback";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "report", label: "最终报告" },
  { key: "outline", label: "目录" },
  { key: "summary", label: "总结" },
  { key: "steps", label: "生成步骤" },
  { key: "chat", label: "追问" },
  { key: "feedback", label: "反馈改写" },
];

function modeLabel(mode: string) {
  if (mode === "advanced") return "高级";
  if (mode === "extended") return "扩展";
  return "标准";
}

function statusClass(status: string) {
  if (status === "completed") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "failed") return "bg-red-50 text-red-700 border-red-200";
  return "bg-amber-50 text-amber-700 border-amber-200";
}

function statusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "cancel_requested") return "正在停止";
  if (status === "cancelled") return "已停止";
  if (status === "parsed") return "已解析";
  if (status === "uploaded") return "已上传";
  if (status === "pending") return "等待生成";
  if (status === "generating_outline") return "生成目录与总结";
  if (status === "generating_chapters") return "分章节讲解";
  if (status === "inserting_images") return "插入图片";
  return status;
}

function stepLabel(stepName: string) {
  if (stepName === "generate_outline") return "生成课程目录与整体总结";
  if (stepName === "apply_image_insert_plan") return "应用插图方案";
  if (stepName === "build_final_report") return "组合最终报告";
  if (stepName.startsWith("generate_chapter_")) return `生成第 ${stepName.replace("generate_chapter_", "")} 章讲解`;
  if (stepName.startsWith("generate_advanced_chapter_")) return `生成第 ${stepName.replace("generate_advanced_chapter_", "")} 章图文讲解`;
  if (stepName.startsWith("extract_extended_knowledge_")) return `提取第 ${stepName.replace("extract_extended_knowledge_", "")} 章知识脉络`;
  if (stepName.startsWith("generate_extended_chapter_")) return `生成第 ${stepName.replace("generate_extended_chapter_", "")} 章拓展讲解`;
  if (stepName.startsWith("generate_image_insert_plan_")) return `判断第 ${stepName.replace("generate_image_insert_plan_", "")} 章插图`;
  return stepName;
}

function progressInfo(report: ReportDetailType, steps: GenerationStep[]) {
  if (report.status === "completed") return { percent: 100, text: "报告已完成", current: "可以查看或下载报告" };
  if (report.status === "failed") return { percent: 100, text: "生成失败", current: "请查看生成步骤中的错误信息" };

  const done = steps.filter((step) => step.status === "completed").length;
  const running = steps.find((step) => step.status === "running");
  const failed = steps.find((step) => step.status === "failed");
  const basePercent =
    report.status === "pending"
      ? 5
      : report.status === "generating_outline"
        ? 15
        : report.status === "generating_chapters"
          ? 45
          : report.status === "inserting_images"
            ? 82
            : 20;
  const stepPercent = steps.length ? Math.min(14, Math.round((done / Math.max(steps.length, 1)) * 14)) : 0;
  return {
    percent: Math.min(96, basePercent + stepPercent),
    text: statusLabel(report.status),
    current: failed ? `失败步骤：${stepLabel(failed.step_name)}` : running ? `当前步骤：${stepLabel(running.step_name)}` : "等待下一步开始",
  };
}

function extractImageNames(markdown: string | null) {
  const names = new Set<string>();
  for (const match of (markdown || "").matchAll(/page_\d{3}\.png/gi)) {
    names.add(match[0]);
  }
  return Array.from(names);
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function pageImageName(page: number) {
  return `page_${String(page).padStart(3, "0")}.png`;
}

function OriginalCoursePanel({ course, targetPage }: { course: Course | null; targetPage?: number | null }) {
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(86);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pageCount = course?.page_count ?? 0;
  const pages = useMemo(() => Array.from({ length: pageCount }, (_, index) => index + 1), [pageCount]);

  useEffect(() => {
    setCurrentPage(1);
  }, [course?.course_id]);

  function scrollToPage(page: number) {
    const element = scrollRef.current?.querySelector<HTMLElement>(`#course-page-${page}`);
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function goToPage(page: number) {
    const next = Math.min(Math.max(page, 1), Math.max(pageCount, 1));
    setCurrentPage(next);
    window.setTimeout(() => scrollToPage(next), 0);
  }

  useEffect(() => {
    if (!targetPage || !pageCount) return;
    const next = Math.min(Math.max(targetPage, 1), pageCount);
    setCurrentPage(next);
    const timers = [80, 220, 520].map((delay) => window.setTimeout(() => scrollToPage(next), delay));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [targetPage, pageCount]);

  if (!course || !pageCount) {
    return (
      <div className="flex h-full min-h-[520px] items-center justify-center rounded border border-dashed border-zinc-300 bg-white text-sm text-zinc-500">
        暂无可对照的课件页。
      </div>
    );
  }

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded border border-zinc-200 bg-zinc-50 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 bg-white px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-zinc-950">
            <BookOpen size={16} />
            <span className="truncate">原课件</span>
          </div>
          <p className="mt-1 truncate text-xs text-zinc-500">{course.title}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            className="inline-flex h-8 w-8 items-center justify-center rounded border border-zinc-200 text-zinc-700 hover:bg-zinc-50 disabled:opacity-40"
            title="上一页"
          >
            <ChevronLeft size={15} />
          </button>
          <input
            value={currentPage}
            onChange={(event) => setCurrentPage(Number(event.target.value) || 1)}
            onBlur={() => goToPage(currentPage)}
            onKeyDown={(event) => {
              if (event.key === "Enter") goToPage(currentPage);
            }}
            className="h-8 w-14 rounded border border-zinc-200 text-center text-sm"
            aria-label="页码"
          />
          <span className="text-xs text-zinc-500">/ {pageCount}</span>
          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= pageCount}
            className="inline-flex h-8 w-8 items-center justify-center rounded border border-zinc-200 text-zinc-700 hover:bg-zinc-50 disabled:opacity-40"
            title="下一页"
          >
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
      <div className="flex items-center gap-3 border-b border-zinc-200 bg-white px-4 py-2">
        <ZoomOut size={15} className="text-zinc-500" />
        <input
          type="range"
          min={62}
          max={116}
          value={zoom}
          onChange={(event) => setZoom(Number(event.target.value))}
          className="w-full accent-zinc-950"
          aria-label="课件缩放"
        />
        <ZoomIn size={15} className="text-zinc-500" />
      </div>
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto px-4 py-5">
        <div className="mx-auto grid gap-5" style={{ width: `${zoom}%`, minWidth: "260px" }}>
          {pages.map((page) => (
            <figure id={`course-page-${page}`} key={page} className="scroll-mt-4 overflow-hidden rounded border border-zinc-200 bg-white shadow-sm">
              <img
                src={courseImageUrl(course.course_id, pageImageName(page))}
                alt={`第 ${page} 页`}
                className="block w-full"
                loading="lazy"
              />
              <figcaption className="border-t border-zinc-200 bg-white px-3 py-2 text-center text-xs text-zinc-500">第 {page} 页</figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  );
}

export function ReportDetail({ reportId, course, onReportChanged }: ReportDetailProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("report");
  const [report, setReport] = useState<ReportDetailType | null>(null);
  const [steps, setSteps] = useState<GenerationStep[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [compareReading, setCompareReading] = useState(false);
  const [splitPercent, setSplitPercent] = useState(48);
  const [highlightSaving, setHighlightSaving] = useState(false);
  const [reportActionBusy, setReportActionBusy] = useState<"delete" | "stop" | null>(null);
  const [targetCoursePage, setTargetCoursePage] = useState<number | null>(null);
  const splitContainerRef = useRef<HTMLDivElement | null>(null);

  async function loadReport(targetReportId: number) {
    setLoading(true);
    setError(null);
    try {
      const [reportPayload, stepPayload] = await Promise.all([getReport(targetReportId), listReportSteps(targetReportId)]);
      setReport(reportPayload);
      setSteps(stepPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载报告失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (reportId) {
      void loadReport(reportId);
    } else {
      setReport(null);
      setSteps([]);
    }
  }, [reportId]);

  useEffect(() => {
    if (!reportId || !report || ["completed", "failed", "cancelled"].includes(report.status)) return;
    const timer = window.setInterval(() => {
      void loadReport(reportId);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [reportId, report?.status]);

  if (!reportId) {
    return (
      <div className="flex min-h-[540px] items-center justify-center rounded border border-dashed border-zinc-300 bg-white text-sm text-zinc-500">
        选择左侧报告后查看内容。
      </div>
    );
  }

  if (loading && !report) {
    return (
      <div className="flex min-h-[540px] items-center justify-center rounded border border-zinc-200 bg-white text-sm text-zinc-500">
        正在加载报告...
      </div>
    );
  }

  if (error) {
    return <div className="rounded border border-red-200 bg-red-50 p-5 text-sm text-red-700">{error}</div>;
  }

  if (!report) return null;

  const currentReport = report;
  const tabMarkdown =
    activeTab === "outline"
      ? currentReport.outline_markdown
      : activeTab === "summary"
        ? currentReport.summary_markdown
        : currentReport.final_markdown;
  const progress = progressInfo(currentReport, steps);
  const totalInputTokens = steps.reduce((sum, step) => sum + (step.input_tokens || 0), 0);
  const totalOutputTokens = steps.reduce((sum, step) => sum + (step.output_tokens || 0), 0);
  const imageNames = extractImageNames(currentReport.final_markdown);
  const canCompare = activeTab === "report";
  const canStop = !["completed", "failed", "cancelled"].includes(currentReport.status);

  async function handleDeleteReport() {
    const confirmed = window.confirm(`确定删除报告 #${currentReport.report_id} 吗？相关问答、反馈和生成步骤也会一起删除。`);
    if (!confirmed) return;
    setReportActionBusy("delete");
    setError(null);
    try {
      await deleteReport(currentReport.report_id);
      onReportChanged?.(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除报告失败");
    } finally {
      setReportActionBusy(null);
    }
  }

  async function handleStopReport() {
    setReportActionBusy("stop");
    setError(null);
    try {
      await stopReportGeneration(currentReport.report_id);
      await loadReport(currentReport.report_id);
      onReportChanged?.(currentReport.report_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "停止报告生成失败");
    } finally {
      setReportActionBusy(null);
    }
  }

  async function handleHighlightSelection(selectedText: string) {
    const markdown = currentReport.final_markdown || "";
    if (!markdown.trim()) return;
    if (!selectedText || selectedText.length < 2) return;

    const escapedText = escapeRegExp(selectedText);
    const markPattern = new RegExp(`<mark(?:\\s+data-note="highlight")?>${escapedText}<\\/mark>|==${escapedText}==`);
    const existingMark = markdown.match(markPattern);
    if (existingMark) {
      const nextMarkdown = markdown.replace(existingMark[0], selectedText);
      setHighlightSaving(true);
      setError(null);
      try {
        await updateReportMarkdown(currentReport.report_id, nextMarkdown);
        setReport({ ...currentReport, final_markdown: nextMarkdown });
        onReportChanged?.(currentReport.report_id);
        window.getSelection()?.removeAllRanges();
      } catch (err) {
        setError(err instanceof Error ? err.message : "取消高亮失败");
      } finally {
        setHighlightSaving(false);
      }
      return;
    }

    const index = markdown.indexOf(selectedText);
    if (index < 0) {
      setError("未能在 Markdown 源文件中定位选中文本，请尝试少选一些连续文字。");
      return;
    }

    const nextMarkdown = `${markdown.slice(0, index)}<mark data-note="highlight">${selectedText}</mark>${markdown.slice(index + selectedText.length)}`;
    setHighlightSaving(true);
    setError(null);
    try {
      await updateReportMarkdown(currentReport.report_id, nextMarkdown);
      setReport({ ...currentReport, final_markdown: nextMarkdown });
      onReportChanged?.(currentReport.report_id);
      window.getSelection()?.removeAllRanges();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存高亮失败");
    } finally {
      setHighlightSaving(false);
    }
  }

  function handlePageRefClick(pageNumber: number) {
    setActiveTab("report");
    setCompareReading(true);
    setTargetCoursePage(null);
    window.setTimeout(() => setTargetCoursePage(pageNumber), 0);
  }

  function handleSplitDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    const container = splitContainerRef.current;
    if (!container) return;

    const update = (clientX: number) => {
      const rect = container.getBoundingClientRect();
      const next = ((clientX - rect.left) / rect.width) * 100;
      setSplitPercent(Math.min(68, Math.max(32, next)));
    };

    update(event.clientX);
    const onPointerMove = (moveEvent: PointerEvent) => update(moveEvent.clientX);
    const onPointerUp = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  }

  return (
    <section className="grid gap-4">
      <div className="rounded border border-zinc-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-zinc-950">报告 #{report.report_id}</h2>
              <span className={`rounded border px-2 py-1 text-xs font-medium ${statusClass(report.status)}`}>{statusLabel(report.status)}</span>
              <span className="rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs text-zinc-600">{modeLabel(report.mode)}模式</span>
            </div>
            <p className="mt-2 break-all text-sm text-zinc-500">{report.report_path || "暂无本地报告路径"}</p>
            <p className="mt-1 text-sm text-zinc-500">Token 估算：输入 {totalInputTokens}，输出 {totalOutputTokens}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => {
                setActiveTab("report");
                setCompareReading((value) => !value);
              }}
              className={`inline-flex h-9 items-center gap-2 rounded border px-3 text-sm ${
                compareReading ? "border-zinc-950 bg-zinc-950 text-white" : "border-zinc-200 text-zinc-700 hover:bg-zinc-50"
              }`}
              title="同时查看原课件和报告"
            >
              <GitCompare size={16} />
              对照阅读
            </button>
            {canStop ? (
              <button
                onClick={() => void handleStopReport()}
                disabled={reportActionBusy !== null}
                className="inline-flex h-9 items-center gap-2 rounded border border-amber-200 px-3 text-sm text-amber-800 hover:bg-amber-50 disabled:opacity-60"
                title="停止生成"
              >
                <Square size={15} />
                停止
              </button>
            ) : null}
            <button
              onClick={() => void handleDeleteReport()}
              disabled={reportActionBusy !== null}
              className="inline-flex h-9 items-center gap-2 rounded border border-red-200 px-3 text-sm text-red-700 hover:bg-red-50 disabled:opacity-60"
              title="删除报告"
            >
              <Trash2 size={16} />
              删除
            </button>
            <a
              href={reportMarkdownDownloadUrl(report.report_id)}
              className="inline-flex h-9 items-center gap-2 rounded border border-zinc-200 px-3 text-sm text-zinc-700 hover:bg-zinc-50"
            >
              <Download size={16} />
              下载 MD
            </a>
            <a
              href={reportPdfDownloadUrl(report.report_id)}
              className="inline-flex h-9 items-center gap-2 rounded border border-zinc-200 px-3 text-sm text-zinc-700 hover:bg-zinc-50"
            >
              <Download size={16} />
              下载 PDF
            </a>
            <button
              onClick={() => void loadReport(report.report_id)}
              className="inline-flex h-9 items-center gap-2 rounded border border-zinc-200 px-3 text-sm text-zinc-700 hover:bg-zinc-50"
            >
              <RefreshCw size={16} />
              刷新
            </button>
          </div>
        </div>

        <div className="mt-4 rounded border border-zinc-200 bg-zinc-50 p-3">
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="font-medium text-zinc-800">{progress.text}</span>
            <span className="text-zinc-500">{progress.percent}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded bg-zinc-200">
            <div className="h-full rounded bg-zinc-950 transition-all" style={{ width: `${progress.percent}%` }} />
          </div>
          <p className="mt-2 text-xs text-zinc-500">{progress.current}</p>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`inline-flex h-9 items-center gap-2 rounded border px-3 text-sm ${
                activeTab === tab.key ? "border-zinc-950 bg-zinc-950 text-white" : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50"
              }`}
            >
              {tab.key === "steps" ? <ListTree size={16} /> : tab.key === "report" ? <FileText size={16} /> : <MessageSquareText size={16} />}
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "steps" ? (
        <StepOutputPanel steps={steps} />
      ) : activeTab === "chat" ? (
        <ChatBox reportId={report.report_id} courseId={report.course_id} imageNames={imageNames} />
      ) : activeTab === "feedback" ? (
        <FeedbackBox
          reportId={report.report_id}
          courseId={report.course_id}
          defaultContent={report.final_markdown || report.content_markdown || ""}
          onApplied={() => void loadReport(report.report_id)}
        />
      ) : (
        <>
          {compareReading && canCompare ? (
            <div
              ref={splitContainerRef}
              className="grid h-[calc(100vh-48px)] min-h-[720px] gap-0 lg:grid-cols-[var(--left)_16px_1fr]"
              style={{ "--left": `${splitPercent}%` } as CSSProperties}
            >
              <div className="min-h-0 min-w-0">
                <OriginalCoursePanel course={course} targetPage={targetCoursePage} />
              </div>
              <button
                type="button"
                onPointerDown={handleSplitDrag}
                className="group hidden cursor-col-resize items-center justify-center lg:flex"
                title="拖动调整分栏宽度"
              >
                <span className="flex h-full w-3 items-center justify-center rounded bg-zinc-100 text-zinc-400 transition group-hover:bg-zinc-200 group-hover:text-zinc-700">
                  <GripVertical size={16} />
                </span>
              </button>
              <div className="mt-4 min-h-0 min-w-0 lg:mt-0">
                <ReportViewer
                  markdown={tabMarkdown || ""}
                  courseId={report.course_id}
                  compactHeader
                  title="讲解报告"
                  onHighlightSelection={handleHighlightSelection}
                  highlightSaving={highlightSaving}
                  onPageRefClick={handlePageRefClick}
                />
              </div>
            </div>
          ) : (
            <ReportViewer
              markdown={tabMarkdown || ""}
              courseId={report.course_id}
              title={activeTab === "report" ? "讲解报告" : undefined}
              onHighlightSelection={activeTab === "report" ? handleHighlightSelection : undefined}
              highlightSaving={highlightSaving}
              onPageRefClick={activeTab === "report" ? handlePageRefClick : undefined}
            />
          )}
        </>
      )}
    </section>
  );
}
