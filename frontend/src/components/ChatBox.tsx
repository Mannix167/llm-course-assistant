import { Loader2, Send } from "lucide-react";
import { useEffect, useState } from "react";

import { askReportQuestion, listChatMessages, listCourseChapters } from "../api/client";
import type { ChapterSummary, ChatMessage, ChatMode, InteractionScope } from "../types";

type ChatBoxProps = {
  reportId: number;
  courseId: number;
  pageCount?: number;
  imageNames?: string[];
};

export function ChatBox({ reportId, courseId, pageCount = 0, imageNames = [] }: ChatBoxProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<ChatMode>("normal");
  const [scope, setScope] = useState<InteractionScope>("report");
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [chapterId, setChapterId] = useState<string>("");
  const [imageName, setImageName] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadMessages() {
    setError(null);
    try {
      setMessages(await listChatMessages(reportId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载追问记录失败");
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

  async function submitQuestion() {
    const trimmed = question.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const payload = await askReportQuestion(reportId, {
        question: trimmed,
        mode,
        scope,
        chapter_id: scope === "chapter" && chapterId ? Number(chapterId) : null,
        page_number: scope === "page" || scope === "image" ? pageNumberFromImage(imageName) ?? pageNumber : null,
        image_name: scope === "image" ? imageName || `page_${String(pageNumber).padStart(3, "0")}.png` : null,
      });
      setMessages((current) => [...current, payload.question, payload.answer]);
      setQuestion("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "追问失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadMessages();
    void loadChapters();
  }, [reportId]);

  useEffect(() => {
    if (imageNames.length && !imageName) setImageName(imageNames[0]);
  }, [imageNames, imageName]);

  return (
    <section className="rounded border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-zinc-950">追问</h3>
          <p className="mt-1 text-sm text-zinc-500">普通追问使用 DeepSeek，高级追问使用 Gemini。回答会附带所选章节或页的课件内容。</p>
        </div>
        <button onClick={() => void loadMessages()} className="rounded border border-zinc-200 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50">
          刷新记录
        </button>
      </div>

      {error ? <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

      <div className="mb-4 max-h-[340px] overflow-auto rounded border border-zinc-200 bg-zinc-50 p-3">
        {messages.map((message) => (
          <div key={message.message_id} className={`mb-3 ${message.role === "user" ? "text-right" : "text-left"}`}>
            <div className={`inline-block max-w-[88%] rounded px-3 py-2 text-sm leading-6 ${message.role === "user" ? "bg-zinc-950 text-white" : "bg-white text-zinc-800"}`}>
              <div className="whitespace-pre-wrap text-left">{message.content}</div>
              <div className={`mt-1 text-xs ${message.role === "user" ? "text-zinc-300" : "text-zinc-400"}`}>
                {message.scope} {message.related_pages.length ? `· 页 ${message.related_pages.join(",")}` : ""}
              </div>
            </div>
          </div>
        ))}
        {!messages.length ? <div className="py-8 text-center text-sm text-zinc-500">暂无追问记录。</div> : null}
      </div>

      <div className="mb-3 grid gap-2 md:grid-cols-[120px_120px_1fr]">
        <select value={mode} onChange={(event) => setMode(event.target.value as ChatMode)} className="h-9 rounded border border-zinc-200 bg-white px-2 text-sm">
          <option value="normal">普通追问</option>
          <option value="advanced">高级追问</option>
        </select>
        <select value={scope} onChange={(event) => setScope(event.target.value as InteractionScope)} className="h-9 rounded border border-zinc-200 bg-white px-2 text-sm">
          <option value="report">整份报告</option>
          <option value="chapter">指定章节</option>
          <option value="page">指定页</option>
          <option value="image">指定插图</option>
        </select>
        {scope === "image" && imageNames.length ? (
          <select
            value={imageName}
            onChange={(event) => setImageName(event.target.value)}
            className="h-9 rounded border border-zinc-200 bg-white px-2 text-sm"
          >
            {imageNames.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        ) : scope === "page" || scope === "image" ? (
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
          <div className="h-9 rounded border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-500">使用整份报告与课件前几页上下文</div>
        )}
      </div>

      <div className="grid gap-2 md:grid-cols-[1fr_auto]">
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          className="min-h-24 rounded border border-zinc-200 p-3 text-sm leading-6"
          placeholder="输入你的问题，例如：这一页为什么要引入这个公式？"
        />
        <button
          onClick={() => void submitQuestion()}
          disabled={loading || !question.trim()}
          className="inline-flex items-center justify-center gap-2 rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {loading ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />}
          发送
        </button>
      </div>
    </section>
  );
}

function pageNumberFromImage(imageName: string) {
  const match = imageName.match(/page_(\d{3})\.png/i);
  return match ? Number(match[1]) : null;
}
