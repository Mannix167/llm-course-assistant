import { Loader2, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";

import { applyFeedbackRewrite, listCourseChapters, listFeedback, submitFeedbackRewrite } from "../api/client";
import type { ChapterSummary, FeedbackItem, InteractionScope } from "../types";

type FeedbackBoxProps = {
  reportId: number;
  courseId: number;
  defaultContent: string;
  pageCount?: number;
  onApplied?: () => void;
};

export function FeedbackBox({ reportId, courseId, defaultContent, pageCount = 0, onApplied }: FeedbackBoxProps) {
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [feedbackText, setFeedbackText] = useState("");
  const [targetContent, setTargetContent] = useState("");
  const [scope, setScope] = useState<InteractionScope>("report");
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [chapterId, setChapterId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadItems() {
    setError(null);
    try {
      setItems(await listFeedback(reportId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载反馈记录失败");
    }
  }

  async function loadChapters() {
    try {
      const payload = await listCourseChapters(courseId);
      setChapters(payload);
      if (payload.length && !chapterId) setChapterId(String(payload[0].chapter_id));
    } catch {
      setChapters([]);
    }
  }

  async function submitFeedback() {
    if (!feedbackText.trim() || !targetContent.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const item = await submitFeedbackRewrite(reportId, {
        feedback_text: feedbackText,
        target_content: targetContent,
        scope,
        chapter_id: scope === "chapter" && chapterId ? Number(chapterId) : null,
        page_number: scope === "page" || scope === "image" ? pageNumber : null,
        image_name: scope === "image" ? `page_${String(pageNumber).padStart(3, "0")}.png` : null,
      });
      setItems((current) => [...current, item]);
      setFeedbackText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "反馈改写失败");
    } finally {
      setLoading(false);
    }
  }

  async function applyRewrite(feedbackId: number) {
    const confirmed = window.confirm("确认将这条改写结果应用到当前报告吗？如果找到原文会替换原文，否则会追加到报告末尾。");
    if (!confirmed) return;
    setLoading(true);
    setError(null);
    try {
      const item = await applyFeedbackRewrite(feedbackId);
      setItems((current) => current.map((existing) => (existing.feedback_id === feedbackId ? item : existing)));
      onApplied?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用改写失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setTargetContent(defaultContent.slice(0, 2500));
  }, [defaultContent, reportId]);

  useEffect(() => {
    void loadItems();
    void loadChapters();
  }, [reportId]);

  return (
    <section className="rounded border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="mb-4">
        <h3 className="text-base font-semibold text-zinc-950">反馈改写</h3>
        <p className="mt-1 text-sm text-zinc-500">选择要改写的内容，说明“太简略、太难懂、需要例子”等反馈，系统会生成局部改写版本。</p>
      </div>
      {error ? <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-3">
        <div className="grid gap-2 md:grid-cols-[120px_1fr]">
          <select value={scope} onChange={(event) => setScope(event.target.value as InteractionScope)} className="h-9 rounded border border-zinc-200 bg-white px-2 text-sm">
            <option value="report">整份报告</option>
            <option value="chapter">指定章节</option>
            <option value="page">指定页</option>
            <option value="image">指定插图</option>
          </select>
          {scope === "page" || scope === "image" ? (
            <input
              type="number"
              min={1}
              max={pageCount || undefined}
              value={pageNumber}
              onChange={(event) => setPageNumber(Number(event.target.value))}
              className="h-9 rounded border border-zinc-200 px-2 text-sm"
              placeholder={scope === "image" ? "插图所在页码" : "页码"}
            />
          ) : scope === "chapter" ? (
            <select
              value={chapterId}
              onChange={(event) => setChapterId(event.target.value)}
              className="h-9 rounded border border-zinc-200 bg-white px-2 text-sm"
            >
              {chapters.map((chapter) => (
                <option key={chapter.chapter_id} value={chapter.chapter_id}>
                  {chapter.title}（{chapter.start_page}-{chapter.end_page}页）
                </option>
              ))}
            </select>
          ) : (
            <div className="h-9 rounded border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-500">使用整份报告上下文</div>
          )}
        </div>
        <textarea
          value={targetContent}
          onChange={(event) => setTargetContent(event.target.value)}
          className="min-h-32 rounded border border-zinc-200 p-3 text-sm leading-6"
          placeholder="粘贴或保留需要改写的报告片段"
        />
        <textarea
          value={feedbackText}
          onChange={(event) => setFeedbackText(event.target.value)}
          className="min-h-20 rounded border border-zinc-200 p-3 text-sm leading-6"
          placeholder="输入反馈，例如：这一段太抽象，请用更通俗的语言并增加例子"
        />
        <button
          onClick={() => void submitFeedback()}
          disabled={loading || !feedbackText.trim() || !targetContent.trim()}
          className="inline-flex h-10 items-center justify-center gap-2 rounded bg-zinc-950 px-4 text-sm font-medium text-white disabled:opacity-60"
        >
          {loading ? <Loader2 className="animate-spin" size={16} /> : <Wand2 size={16} />}
          生成改写版本
        </button>
      </div>

      <div className="mt-5 grid gap-3">
        <h4 className="text-sm font-semibold text-zinc-900">反馈记录</h4>
        {items.map((item) => (
          <div key={item.feedback_id} className="rounded border border-zinc-200 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
              <span>#{item.feedback_id}</span>
              <span>{item.target_type}</span>
              <span>{item.status}</span>
            </div>
            <p className="mb-3 text-sm text-zinc-700">{item.feedback_text}</p>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-3 text-sm leading-6 text-zinc-800">{item.result_content || "暂无改写结果"}</pre>
            {item.status === "completed" && item.result_content ? (
              <button
                onClick={() => void applyRewrite(item.feedback_id)}
                disabled={loading}
                className="mt-3 rounded bg-zinc-950 px-3 py-1.5 text-sm text-white disabled:opacity-60"
              >
                确认应用到报告
              </button>
            ) : null}
          </div>
        ))}
        {!items.length ? <div className="rounded border border-dashed border-zinc-300 p-4 text-sm text-zinc-500">暂无反馈记录。</div> : null}
      </div>
    </section>
  );
}
