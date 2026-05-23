export type ReportMode = "standard" | "advanced" | "extended";

export type Course = {
  course_id: number;
  folder_id: number | null;
  folder_name: string | null;
  title: string;
  file_name: string;
  file_type: string;
  page_count: number;
  status: string;
  scanned_like: boolean;
  report_count: number;
  created_at: string | null;
  updated_at: string | null;
};

export type CourseFolder = {
  folder_id: number;
  name: string;
  description: string | null;
  course_count: number;
  created_at: string | null;
  updated_at: string | null;
};

export type ChapterSummary = {
  chapter_id: number;
  title: string;
  start_page: number;
  end_page: number;
  key_points: string[];
  order_index: number;
};

export type ReportSummary = {
  report_id: number;
  course_id: number;
  mode: ReportMode;
  status: string;
  report_path: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ReportDetail = ReportSummary & {
  outline_markdown: string | null;
  summary_markdown: string | null;
  content_markdown: string | null;
  final_markdown: string | null;
  review_result: string | null;
};

export type GenerationStep = {
  step_id: number;
  course_id: number;
  report_id: number;
  step_name: string;
  status: string;
  input_preview: string | null;
  output_content: string | null;
  input_tokens: number;
  output_tokens: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type ChatMode = "normal" | "advanced";
export type InteractionScope = "report" | "chapter" | "page" | "image";

export type ChatMessage = {
  message_id: number;
  course_id: number;
  report_id: number;
  role: "user" | "assistant";
  content: string;
  scope: InteractionScope;
  related_pages: number[];
  related_chapter_id: number | null;
  created_at: string | null;
};

export type ChatResponse = {
  question: ChatMessage;
  answer: ChatMessage;
  context_preview: string;
};

export type FeedbackItem = {
  feedback_id: number;
  course_id: number;
  report_id: number;
  target_type: InteractionScope;
  target_id: number | null;
  feedback_text: string;
  target_content: string | null;
  status: string;
  result_content: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ModelPurposeConfig = {
  provider: string;
  model: string;
  provider_env: string;
  model_env: string;
};

export type ProviderConfig = {
  base_url: string;
  has_api_key: boolean;
  api_key?: string;
};

export type ModelConfig = {
  purposes: Record<string, ModelPurposeConfig>;
  providers: Record<string, ProviderConfig>;
  provider_options: string[];
};
