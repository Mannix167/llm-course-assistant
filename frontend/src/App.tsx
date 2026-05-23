import {
  BookOpen,
  Edit3,
  FileText,
  Folder,
  FolderPlus,
  GitCompare,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  RefreshCw,
  Search,
  Settings,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { createRoot } from "react-dom/client";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  createFolder,
  createReport,
  deleteFolder,
  getReport,
  listCourses,
  listFolders,
  listReports,
  moveCourseToFolder,
  parseCourse,
  updateFolder,
  uploadPdf,
} from "./api/client";
import { ModelSettingsPanel } from "./components/ModelSettingsPanel";
import { ReportDetail } from "./pages/ReportDetail";
import type { Course, CourseFolder, ReportDetail as ReportDetailType, ReportMode, ReportSummary } from "./types";
import "./styles.css";

const modes: Array<{ value: ReportMode; label: string; description: string }> = [
  { value: "standard", label: "标准", description: "文字生成后自动插入候选图片" },
  { value: "advanced", label: "高级", description: "章节生成时同时参考文字和候选图片" },
  { value: "extended", label: "扩展", description: "先抽取知识脉络，再生成拓展讲解" },
];

function modeLabel(mode: string) {
  return modes.find((item) => item.value === mode)?.label ?? mode;
}

function statusClass(status: string) {
  if (status === "completed" || status === "parsed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "failed") return "border-red-200 bg-red-50 text-red-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function statusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "parsed") return "已解析";
  if (status === "uploaded") return "已上传";
  if (status === "failed") return "失败";
  if (status === "cancel_requested") return "正在停止";
  if (status === "cancelled") return "已停止";
  if (status === "pending") return "等待中";
  if (status === "generating_outline") return "生成目录";
  if (status === "generating_chapters") return "生成章节";
  if (status === "inserting_images") return "插入图片";
  return status;
}

function reportSearchText(report: ReportSummary) {
  return [
    `#${report.report_id}`,
    String(report.report_id),
    modeLabel(report.mode),
    report.mode,
    statusLabel(report.status),
    report.status,
    report.report_path ?? "",
    report.created_at ?? "",
  ]
    .join(" ")
    .toLowerCase();
}

function formatTime(value: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function folderFilterMatches(course: Course, selectedFolderId: number | "all" | "unfiled") {
  if (selectedFolderId === "all") return true;
  if (selectedFolderId === "unfiled") return course.folder_id === null;
  return course.folder_id === selectedFolderId;
}

function currentFolderName(selectedFolderId: number | "all" | "unfiled", folders: CourseFolder[]) {
  if (selectedFolderId === "all") return "全部课件";
  if (selectedFolderId === "unfiled") return "未归档";
  return folders.find((folder) => folder.folder_id === selectedFolderId)?.name ?? "未知文件夹";
}

function App() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [folders, setFolders] = useState<CourseFolder[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<number | "all" | "unfiled">("all");
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [mode, setMode] = useState<ReportMode>("standard");
  const [loadingCourses, setLoadingCourses] = useState(false);
  const [busyAction, setBusyAction] = useState<"upload" | "parse" | "report" | "folder" | "move" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const [renameFolderName, setRenameFolderName] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(null);
  const [actionFolderId, setActionFolderId] = useState<number | null>(null);
  const [reportSearch, setReportSearch] = useState("");
  const [compareReportIds, setCompareReportIds] = useState<number[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareReports, setCompareReports] = useState<ReportDetailType[]>([]);
  const [loadingCompare, setLoadingCompare] = useState(false);
  const [completionNotice, setCompletionNotice] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const knownReportStatuses = useRef<Record<number, string>>({});

  const selectedCourse = useMemo(
    () => courses.find((course) => course.course_id === selectedCourseId) ?? null,
    [courses, selectedCourseId],
  );
  const selectedMode = modes.find((item) => item.value === mode) ?? modes[0];
  const filteredCourses = useMemo(
    () => courses.filter((course) => folderFilterMatches(course, selectedFolderId)),
    [courses, selectedFolderId],
  );
  const filteredReports = useMemo(() => {
    const query = reportSearch.trim().toLowerCase();
    if (!query) return reports;
    return reports.filter((report) => reportSearchText(report).includes(query));
  }, [reports, reportSearch]);
  const selectedFolder = typeof selectedFolderId === "number" ? folders.find((folder) => folder.folder_id === selectedFolderId) ?? null : null;

  async function refreshFolders() {
    setFolders(await listFolders());
  }

  async function refreshCourses(preferredCourseId?: number | null) {
    setLoadingCourses(true);
    setError(null);
    try {
      const [coursePayload, folderPayload] = await Promise.all([listCourses(), listFolders()]);
      setCourses(coursePayload);
      setFolders(folderPayload);
      const visibleCourses = coursePayload.filter((course) => folderFilterMatches(course, selectedFolderId));
      const lastCourse = visibleCourses.length ? visibleCourses[visibleCourses.length - 1] : coursePayload[coursePayload.length - 1] ?? null;
      setSelectedCourseId(preferredCourseId ?? selectedCourseId ?? lastCourse?.course_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载课件失败");
    } finally {
      setLoadingCourses(false);
    }
  }

  async function refreshReports(courseId: number, preferredReportId?: number | null) {
    setError(null);
    try {
      const payload = await listReports(courseId);
      setReports(payload);
      const lastReport = payload.length ? payload[payload.length - 1] : null;
      setSelectedReportId(preferredReportId ?? lastReport?.report_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载报告列表失败");
    }
  }

  async function handleCreateFolder() {
    const name = newFolderName.trim();
    if (!name) return;
    setBusyAction("folder");
    setError(null);
    try {
      const folder = await createFolder(name);
      setNewFolderName("");
      setSelectedFolderId(folder.folder_id);
      await refreshCourses(selectedCourseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建文件夹失败");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleRenameFolder() {
    if (!selectedFolder || !renameFolderName.trim()) return;
    setBusyAction("folder");
    setError(null);
    try {
      await updateFolder(selectedFolder.folder_id, renameFolderName.trim());
      await refreshCourses(selectedCourseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重命名文件夹失败");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDeleteSelectedFolder() {
    if (!selectedFolder) return;
    const confirmed = window.confirm(`确定删除文件夹“${selectedFolder.name}”吗？其中课件会移动到“未归档”，不会被删除。`);
    if (!confirmed) return;
    setBusyAction("folder");
    setError(null);
    try {
      await deleteFolder(selectedFolder.folder_id);
      setSelectedFolderId("all");
      await refreshCourses(selectedCourseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除文件夹失败");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleConfirmAndGenerate() {
    setBusyAction("report");
    setError(null);
    try {
      let targetCourseId = selectedCourseId;
      let targetStatus = selectedCourse?.status ?? "";

      if (selectedUploadFile) {
        const uploaded = await uploadPdf(selectedUploadFile, actionFolderId);
        targetCourseId = uploaded.course_id;
        targetStatus = uploaded.status;
      } else if (!targetCourseId) {
        throw new Error("请先选择一个课件，或上传一个新的 PDF。");
      } else if ((selectedCourse?.folder_id ?? null) !== actionFolderId) {
        await moveCourseToFolder(targetCourseId, actionFolderId);
      }

      if (targetStatus !== "parsed") {
        await parseCourse(targetCourseId);
      }

      const created = await createReport(targetCourseId, mode);
      setSelectedCourseId(targetCourseId);
      setSelectedReportId(created.report_id);
      await refreshCourses(targetCourseId);
      await refreshReports(targetCourseId, created.report_id);
      setSelectedUploadFile(null);
      setActionsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成报告失败");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleMoveOnly() {
    if (!selectedCourseId || (selectedCourse?.folder_id ?? null) === actionFolderId) return;
    setBusyAction("move");
    setError(null);
    try {
      await moveCourseToFolder(selectedCourseId, actionFolderId);
      await refreshCourses(selectedCourseId);
      await refreshReports(selectedCourseId, selectedReportId);
      setActionsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "移动文件夹失败");
    } finally {
      setBusyAction(null);
    }
  }

  function toggleCompareReport(reportId: number) {
    setCompareReportIds((current) => {
      if (current.includes(reportId)) return current.filter((id) => id !== reportId);
      return [...current.slice(-1), reportId];
    });
  }

  async function handleOpenCompare() {
    if (compareReportIds.length !== 2) return;
    setLoadingCompare(true);
    setError(null);
    try {
      const payload = await Promise.all(compareReportIds.map((reportId) => getReport(reportId)));
      setCompareReports(payload);
      setCompareOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载对比报告失败");
    } finally {
      setLoadingCompare(false);
    }
  }

  async function handleReportChanged(preferredReportId?: number | null) {
    if (!selectedCourseId) return;
    await refreshReports(selectedCourseId, preferredReportId);
  }

  useEffect(() => {
    void refreshCourses();
  }, []);

  useEffect(() => {
    if (selectedCourseId) {
      void refreshReports(selectedCourseId);
    } else {
      setReports([]);
      setSelectedReportId(null);
    }
    setCompareReportIds([]);
    setReportSearch("");
  }, [selectedCourseId]);

  useEffect(() => {
    if (selectedCourse && !folderFilterMatches(selectedCourse, selectedFolderId)) {
      const nextCourse = filteredCourses[0] ?? null;
      setSelectedCourseId(nextCourse?.course_id ?? null);
    }
  }, [filteredCourses, selectedCourse, selectedFolderId]);

  useEffect(() => {
    setRenameFolderName(selectedFolder?.name ?? "");
  }, [selectedFolder?.folder_id, selectedFolder?.name]);

  useEffect(() => {
    if (actionsOpen) {
      setActionFolderId(selectedCourse?.folder_id ?? (typeof selectedFolderId === "number" ? selectedFolderId : null));
      setSelectedUploadFile(null);
    }
  }, [actionsOpen, selectedCourse?.folder_id, selectedFolderId]);

  useEffect(() => {
    if (!selectedCourseId || !reports.some((report) => !["completed", "failed", "cancelled"].includes(report.status))) return;
    const timer = window.setInterval(() => {
      void refreshReports(selectedCourseId, selectedReportId);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [selectedCourseId, selectedReportId, reports]);

  useEffect(() => {
    for (const report of reports) {
      const previousStatus = knownReportStatuses.current[report.report_id];
      if (previousStatus && !["completed", "failed", "cancelled"].includes(previousStatus) && report.status === "completed") {
        setCompletionNotice(`报告 #${report.report_id} 已生成完成`);
      }
      knownReportStatuses.current[report.report_id] = report.status;
    }
  }, [reports]);

  useEffect(() => {
    if (!completionNotice) return;
    const timer = window.setTimeout(() => setCompletionNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [completionNotice]);

  return (
    <main className="min-h-screen bg-zinc-100 text-zinc-950">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded bg-zinc-950 text-white">
              <BookOpen size={20} />
            </div>
            <div>
              <h1 className="text-lg font-semibold">课件学习助手</h1>
              <p className="text-sm text-zinc-500">管理课件文件夹，配置模型接口，生成学习报告。</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarCollapsed((value) => !value)}
              className="inline-flex h-9 items-center gap-2 rounded border border-zinc-200 px-3 text-sm text-zinc-700 hover:bg-zinc-50"
              title={sidebarCollapsed ? "展开左侧栏" : "收起左侧栏"}
            >
              {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
              {sidebarCollapsed ? "展开侧栏" : "收起侧栏"}
            </button>
            <button
              onClick={() => setActionsOpen(true)}
              className="inline-flex h-9 items-center gap-2 rounded bg-zinc-950 px-3 text-sm text-white hover:bg-zinc-800"
            >
              <Upload size={16} />
              导入与生成
            </button>
            <button
              onClick={() => setSettingsOpen(true)}
              className="inline-flex h-9 items-center gap-2 rounded border border-zinc-200 px-3 text-sm text-zinc-700 hover:bg-zinc-50"
            >
              <Settings size={16} />
              模型配置
            </button>
            <button
              onClick={() => void refreshCourses(selectedCourseId)}
              className="inline-flex h-9 items-center gap-2 rounded border border-zinc-200 px-3 text-sm text-zinc-700 hover:bg-zinc-50"
            >
              <RefreshCw size={16} />
              刷新
            </button>
          </div>
        </div>
      </header>

      {completionNotice ? (
        <div className="fixed right-5 top-20 z-40 flex max-w-sm items-center justify-between gap-3 rounded border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 shadow-lg">
          <span>{completionNotice}</span>
          <button onClick={() => setCompletionNotice(null)} className="rounded p-1 hover:bg-emerald-100" title="关闭通知">
            <X size={14} />
          </button>
        </div>
      ) : null}

      <div className={`mx-auto grid gap-5 px-5 py-5 ${sidebarCollapsed ? "max-w-none xl:grid-cols-1" : "max-w-[1600px] xl:grid-cols-[380px_1fr]"}`}>
        {!sidebarCollapsed ? (
        <aside className="grid content-start gap-4">
          <section className="rounded border border-zinc-200 bg-white shadow-sm">
            <div className="border-b border-zinc-200 px-4 py-3">
              <h2 className="text-sm font-semibold text-zinc-900">课程文件夹</h2>
              <p className="mt-1 text-xs text-zinc-500">管理不同课程下的多个课件</p>
            </div>
            <div className="p-3">
              <div className="mb-3 grid grid-cols-[1fr_auto] gap-2">
                <input
                  value={newFolderName}
                  onChange={(event) => setNewFolderName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void handleCreateFolder();
                  }}
                  className="h-9 rounded border border-zinc-200 px-2 text-sm"
                  placeholder="新建文件夹"
                />
                <button
                  onClick={() => void handleCreateFolder()}
                  disabled={busyAction !== null || !newFolderName.trim()}
                  className="inline-flex h-9 items-center justify-center rounded bg-zinc-950 px-3 text-white disabled:opacity-60"
                  title="新建文件夹"
                >
                  {busyAction === "folder" ? <Loader2 className="animate-spin" size={16} /> : <FolderPlus size={16} />}
                </button>
              </div>
              <div className="grid gap-2">
                <button
                  onClick={() => setSelectedFolderId("all")}
                  className={`flex items-center justify-between rounded border px-3 py-2 text-left text-sm ${
                    selectedFolderId === "all" ? "border-zinc-950 bg-zinc-950 text-white" : "border-zinc-200 hover:bg-zinc-50"
                  }`}
                >
                  <span className="inline-flex items-center gap-2"><Folder size={15} />全部课件</span>
                  <span>{courses.length}</span>
                </button>
                <button
                  onClick={() => setSelectedFolderId("unfiled")}
                  className={`flex items-center justify-between rounded border px-3 py-2 text-left text-sm ${
                    selectedFolderId === "unfiled" ? "border-zinc-950 bg-zinc-950 text-white" : "border-zinc-200 hover:bg-zinc-50"
                  }`}
                >
                  <span className="inline-flex items-center gap-2"><Folder size={15} />未归档</span>
                  <span>{courses.filter((course) => course.folder_id === null).length}</span>
                </button>
                {folders.map((folder) => (
                  <button
                    key={folder.folder_id}
                    onClick={() => setSelectedFolderId(folder.folder_id)}
                    className={`flex items-center justify-between rounded border px-3 py-2 text-left text-sm ${
                      selectedFolderId === folder.folder_id ? "border-zinc-950 bg-zinc-950 text-white" : "border-zinc-200 hover:bg-zinc-50"
                    }`}
                  >
                    <span className="inline-flex min-w-0 items-center gap-2">
                      <Folder size={15} />
                      <span className="truncate">{folder.name}</span>
                    </span>
                    <span>{folder.course_count}</span>
                  </button>
                ))}
              </div>
              {selectedFolder ? (
                <div className="mt-3 rounded border border-zinc-200 bg-zinc-50 p-3">
                  <label className="text-xs font-medium text-zinc-600">重命名当前文件夹</label>
                  <div className="mt-2 grid grid-cols-[1fr_auto_auto] gap-2">
                    <input
                      value={renameFolderName}
                      onChange={(event) => setRenameFolderName(event.target.value)}
                      className="h-9 rounded border border-zinc-200 px-2 text-sm"
                    />
                    <button
                      onClick={() => void handleRenameFolder()}
                      disabled={busyAction !== null || !renameFolderName.trim()}
                      className="inline-flex h-9 items-center justify-center rounded border border-zinc-200 px-3 text-zinc-700 hover:bg-white disabled:opacity-60"
                      title="重命名"
                    >
                      <Edit3 size={15} />
                    </button>
                    <button
                      onClick={() => void handleDeleteSelectedFolder()}
                      disabled={busyAction !== null}
                      className="inline-flex h-9 items-center justify-center rounded border border-red-200 px-3 text-red-700 hover:bg-red-50 disabled:opacity-60"
                      title="删除文件夹"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </section>

          <section className="rounded border border-zinc-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-zinc-900">课件列表</h2>
                <p className="mt-1 text-xs text-zinc-500">{loadingCourses ? "加载中..." : `${currentFolderName(selectedFolderId, folders)} · ${filteredCourses.length} 份`}</p>
              </div>
              <button
                onClick={() => setActionsOpen(true)}
                className="rounded border border-zinc-200 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50"
              >
                操作
              </button>
            </div>
            <div className="max-h-[300px] overflow-auto">
              {filteredCourses.map((course) => (
                <button
                  key={course.course_id}
                  onClick={() => setSelectedCourseId(course.course_id)}
                  className={`w-full border-b border-zinc-100 px-4 py-3 text-left hover:bg-zinc-50 ${
                    selectedCourseId === course.course_id ? "bg-zinc-100" : "bg-white"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <FileText className="mt-0.5 shrink-0 text-zinc-500" size={17} />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-zinc-950">{course.title}</p>
                      <p className="mt-1 text-xs text-zinc-500">
                        {course.folder_name || "未归档"} · {course.page_count} 页 · {course.report_count} 份报告
                      </p>
                      <span className={`mt-2 inline-flex rounded border px-2 py-0.5 text-xs ${statusClass(course.status)}`}>{statusLabel(course.status)}</span>
                    </div>
                  </div>
                </button>
              ))}
              {!filteredCourses.length && !loadingCourses ? <div className="p-5 text-sm text-zinc-500">当前文件夹暂无课件。</div> : null}
            </div>
          </section>

          {selectedCourse ? (
            <section className="rounded border border-zinc-200 bg-white shadow-sm">
              <div className="border-b border-zinc-200 px-4 py-3">
                <h2 className="truncate text-sm font-semibold text-zinc-900">{selectedCourse.title}</h2>
                <p className="mt-1 text-xs text-zinc-500">
                  {selectedCourse.folder_name || "未归档"} · {selectedCourse.page_count || "-"} 页 · {statusLabel(selectedCourse.status)}
                </p>
              </div>
              <div className="grid gap-2 p-4 text-xs text-zinc-500">
                <div>文件：{selectedCourse.file_name}</div>
                <div>更新时间：{formatTime(selectedCourse.updated_at)}</div>
              </div>
              <div className="border-t border-zinc-200 px-4 py-3">
                <h3 className="mb-2 text-sm font-semibold text-zinc-900">报告版本</h3>
                <div className="mb-3 grid gap-2">
                  <div className="flex items-center gap-2">
                    <div className="relative min-w-0 flex-1">
                      <Search className="pointer-events-none absolute left-2 top-2.5 text-zinc-400" size={14} />
                      <input
                        value={reportSearch}
                        onChange={(event) => setReportSearch(event.target.value)}
                        className="h-9 w-full rounded border border-zinc-200 pl-8 pr-3 text-sm"
                        placeholder="搜索报告编号、模式、状态"
                      />
                    </div>
                    <button
                      onClick={() => void handleOpenCompare()}
                      disabled={compareReportIds.length !== 2 || loadingCompare}
                      className="inline-flex h-9 items-center gap-1 rounded border border-zinc-200 px-3 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
                    >
                      {loadingCompare ? <Loader2 className="animate-spin" size={14} /> : <GitCompare size={14} />}
                      对比
                    </button>
                  </div>
                  <p className="text-xs text-zinc-500">勾选两个报告版本后点击“对比”。</p>
                </div>
                <div className="max-h-[230px] overflow-auto">
                  {filteredReports.map((report) => (
                    <button
                      key={report.report_id}
                      onClick={() => setSelectedReportId(report.report_id)}
                      className={`mb-2 w-full rounded border px-3 py-2 text-left hover:bg-zinc-50 ${
                        selectedReportId === report.report_id ? "border-zinc-950 bg-zinc-100" : "border-zinc-200 bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-zinc-950">报告 #{report.report_id} · {modeLabel(report.mode)}模式</p>
                          <p className="mt-1 text-xs text-zinc-500">{formatTime(report.created_at)}</p>
                        </div>
                        <span className={`shrink-0 rounded border px-2 py-0.5 text-xs ${statusClass(report.status)}`}>{statusLabel(report.status)}</span>
                        <span
                          onClick={(event) => event.stopPropagation()}
                          className="inline-flex shrink-0 items-center gap-1 text-xs text-zinc-500"
                          title="加入版本对比"
                        >
                          <input
                            type="checkbox"
                            checked={compareReportIds.includes(report.report_id)}
                            onChange={() => toggleCompareReport(report.report_id)}
                          />
                          对比
                        </span>
                      </div>
                    </button>
                  ))}
                  {!reports.length ? <div className="rounded border border-dashed border-zinc-300 p-4 text-sm text-zinc-500">当前课件暂无报告。</div> : null}
                </div>
              </div>
            </section>
          ) : null}
        </aside>
        ) : null}

        <section className="min-w-0">
          {error ? <div className="mb-4 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
          <ReportDetail reportId={selectedReportId} course={selectedCourse} onReportChanged={handleReportChanged} />
        </section>
      </div>

      {actionsOpen ? (
        <div className="fixed inset-0 z-30 bg-black/30 px-4 py-6">
          <div className="mx-auto max-w-2xl rounded border border-zinc-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4">
              <div>
                <h2 className="text-base font-semibold text-zinc-950">导入、解析与生成</h2>
                <p className="mt-1 text-sm text-zinc-500">这些操作会改变课件或调用大模型，因此集中放在这里。</p>
              </div>
              <button onClick={() => setActionsOpen(false)} className="rounded border border-zinc-200 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50">
                关闭
              </button>
            </div>
            <div className="grid gap-4 p-5">
              <section className="grid gap-3 rounded border border-zinc-200 p-4">
                <h3 className="text-sm font-semibold text-zinc-900">选择课件</h3>
                <div className="rounded bg-zinc-50 p-3 text-sm text-zinc-600">
                  {selectedUploadFile
                    ? `新上传文件：${selectedUploadFile.name}`
                    : selectedCourse
                      ? `当前课件：${selectedCourse.title}`
                      : "请选择已有课件，或上传一个新的 PDF。"}
                </div>
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(event) => setSelectedUploadFile(event.target.files?.[0] ?? null)}
                  className="block w-full rounded border border-zinc-200 px-3 py-2 text-sm"
                />
              </section>

              <section className="grid gap-3 rounded border border-zinc-200 p-4">
                <h3 className="text-sm font-semibold text-zinc-900">保存位置与生成模式</h3>
                <label className="text-xs font-medium text-zinc-500">文件夹</label>
                <select
                  value={actionFolderId ?? ""}
                  onChange={(event) => setActionFolderId(event.target.value ? Number(event.target.value) : null)}
                  disabled={busyAction !== null}
                  className="h-9 rounded border border-zinc-200 bg-white px-3 text-sm text-zinc-800"
                >
                  <option value="">未归档</option>
                  {folders.map((folder) => (
                    <option key={folder.folder_id} value={folder.folder_id}>{folder.name}</option>
                  ))}
                </select>

                <label className="text-xs font-medium text-zinc-500">报告模式</label>
                <select
                  value={mode}
                  onChange={(event) => setMode(event.target.value as ReportMode)}
                  className="h-9 rounded border border-zinc-200 bg-white px-3 text-sm text-zinc-800"
                >
                  {modes.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}模式</option>
                  ))}
                </select>
                <p className="text-xs leading-5 text-zinc-500">{selectedMode.description}</p>
              </section>

              <section className="rounded border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800">
                点击“确认并生成报告”会自动完成上传、解析和生成报告。若只是调整当前课件所在文件夹，请点击“仅移动文件夹”，不会调用大模型。
              </section>
            </div>
            <div className="flex justify-end gap-2 border-t border-zinc-200 px-5 py-4">
              <button
                onClick={() => setActionsOpen(false)}
                disabled={busyAction !== null}
                className="rounded border border-zinc-200 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
              >
                取消
              </button>
              <button
                onClick={() => void handleMoveOnly()}
                disabled={busyAction !== null || Boolean(selectedUploadFile) || !selectedCourse || (selectedCourse.folder_id ?? null) === actionFolderId}
                className="inline-flex items-center gap-2 rounded border border-zinc-200 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
              >
                {busyAction === "move" ? <Loader2 className="animate-spin" size={16} /> : <Folder size={16} />}
                仅移动文件夹
              </button>
              <button
                onClick={() => void handleConfirmAndGenerate()}
                disabled={busyAction !== null || (!selectedCourse && !selectedUploadFile)}
                className="inline-flex items-center gap-2 rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {busyAction === "report" ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}
                确认并生成报告
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {compareOpen ? (
        <div className="fixed inset-0 z-30 bg-black/30 px-4 py-6">
          <div className="mx-auto flex max-h-[92vh] max-w-6xl flex-col rounded border border-zinc-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4">
              <div>
                <h2 className="text-base font-semibold text-zinc-950">报告版本对比</h2>
                <p className="mt-1 text-sm text-zinc-500">左右查看两个版本的最终 Markdown 内容。</p>
              </div>
              <button onClick={() => setCompareOpen(false)} className="rounded border border-zinc-200 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50">
                关闭
              </button>
            </div>
            <div className="grid min-h-0 gap-4 overflow-auto p-5 lg:grid-cols-2">
              {compareReports.map((report) => (
                <section key={report.report_id} className="min-w-0 rounded border border-zinc-200">
                  <div className="border-b border-zinc-200 bg-zinc-50 px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-zinc-950">报告 #{report.report_id}</h3>
                      <span className={`rounded border px-2 py-0.5 text-xs ${statusClass(report.status)}`}>{statusLabel(report.status)}</span>
                      <span className="rounded border border-zinc-200 bg-white px-2 py-0.5 text-xs text-zinc-600">{modeLabel(report.mode)}模式</span>
                    </div>
                    <p className="mt-1 text-xs text-zinc-500">{formatTime(report.created_at)}</p>
                  </div>
                  <pre className="max-h-[68vh] overflow-auto whitespace-pre-wrap break-words p-4 text-xs leading-5 text-zinc-700">
                    {report.final_markdown || report.content_markdown || "该报告暂无可对比内容。"}
                  </pre>
                </section>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      <ModelSettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
