import type {
  ChatMode,
  ChatMessage,
  ChatResponse,
  ChapterSummary,
  Course,
  CourseFolder,
  FeedbackItem,
  GenerationStep,
  InteractionScope,
  ModelConfig,
  ReportDetail,
  ReportMode,
  ReportSummary,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      message = payload.detail ?? message;
    } catch {
      // Keep the HTTP status text when the body is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function getHealth() {
  return requestJson<{ status: string }>("/api/health");
}

export async function listCourses() {
  return requestJson<Course[]>("/api/courses");
}

export async function listFolders() {
  return requestJson<CourseFolder[]>("/api/folders");
}

export async function createFolder(name: string, description?: string) {
  return requestJson<CourseFolder>("/api/folders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
}

export async function updateFolder(folderId: number, name: string, description?: string) {
  return requestJson<CourseFolder>(`/api/folders/${folderId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
}

export async function deleteFolder(folderId: number) {
  return requestJson<{ deleted: boolean }>(`/api/folders/${folderId}`, { method: "DELETE" });
}

export async function moveCourseToFolder(courseId: number, folderId: number | null) {
  return requestJson<{ course_id: number; folder_id: number | null; folder_name: string | null }>(
    `/api/courses/${courseId}/folder`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_id: folderId }),
    },
  );
}

export async function uploadPdf(file: File, folderId?: number | null) {
  const formData = new FormData();
  formData.append("file", file);
  if (folderId) {
    formData.append("folder_id", String(folderId));
  }
  return requestJson<{ course_id: number; status: string }>("/api/upload", {
    method: "POST",
    body: formData,
  });
}

export async function getModelConfig() {
  return requestJson<ModelConfig>("/api/settings/model-config");
}

export async function updateModelConfig(config: Partial<ModelConfig>) {
  return requestJson<ModelConfig>("/api/settings/model-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
}

export async function testModelConfig(provider: string, model: string) {
  return requestJson<{ ok: boolean; provider: string; model: string; response_preview: string }>("/api/settings/model-config/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, model }),
  });
}

export async function listReports(courseId: number) {
  return requestJson<ReportSummary[]>(`/api/courses/${courseId}/reports`);
}

export async function listCourseChapters(courseId: number) {
  return requestJson<ChapterSummary[]>(`/api/courses/${courseId}/chapters`);
}

export async function getReport(reportId: number) {
  return requestJson<ReportDetail>(`/api/reports/${reportId}`);
}

export async function listReportSteps(reportId: number) {
  return requestJson<GenerationStep[]>(`/api/reports/${reportId}/steps`);
}

export async function listChatMessages(reportId: number) {
  return requestJson<ChatMessage[]>(`/api/reports/${reportId}/chat`);
}

export async function askReportQuestion(
  reportId: number,
  payload: {
    question: string;
    mode: ChatMode;
    scope: InteractionScope;
    chapter_id?: number | null;
    page_number?: number | null;
    image_name?: string | null;
  },
) {
  return requestJson<ChatResponse>(`/api/reports/${reportId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function listFeedback(reportId: number) {
  return requestJson<FeedbackItem[]>(`/api/reports/${reportId}/feedback`);
}

export async function submitFeedbackRewrite(
  reportId: number,
  payload: {
    feedback_text: string;
    target_content: string;
    scope: InteractionScope;
    chapter_id?: number | null;
    page_number?: number | null;
    image_name?: string | null;
  },
) {
  return requestJson<FeedbackItem>(`/api/reports/${reportId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function applyFeedbackRewrite(feedbackId: number) {
  return requestJson<FeedbackItem>(`/api/feedback/${feedbackId}/apply`, { method: "POST" });
}

export async function parseCourse(courseId: number) {
  return requestJson<{ course_id: number; status: string; page_count: number; scanned_like: boolean }>(
    `/api/courses/${courseId}/parse`,
    { method: "POST" },
  );
}

export async function createReport(courseId: number, mode: ReportMode) {
  return requestJson<{ report_id: number; course_id: number; mode: ReportMode; status: string }>(
    `/api/courses/${courseId}/reports`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    },
  );
}

export async function deleteReport(reportId: number) {
  return requestJson<{ deleted: boolean }>(`/api/reports/${reportId}`, { method: "DELETE" });
}

export async function stopReportGeneration(reportId: number) {
  return requestJson<{ report_id: number; status: string }>(`/api/reports/${reportId}/stop`, { method: "POST" });
}

export async function updateReportMarkdown(reportId: number, finalMarkdown: string) {
  return requestJson<Partial<ReportDetail>>(`/api/reports/${reportId}/markdown`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ final_markdown: finalMarkdown }),
  });
}

export function courseImageUrl(courseId: number, imageName: string) {
  return `${API_BASE_URL}/api/courses/${courseId}/images/${encodeURIComponent(imageName)}`;
}

export function reportMarkdownDownloadUrl(reportId: number) {
  return `${API_BASE_URL}/api/reports/${reportId}/download.md`;
}

export function reportPdfDownloadUrl(reportId: number) {
  return `${API_BASE_URL}/api/reports/${reportId}/download.pdf`;
}
