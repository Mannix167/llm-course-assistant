import { CheckCircle2, CircleAlert, Clock3, PlayCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { GenerationStep } from "../types";

type StepOutputPanelProps = {
  steps: GenerationStep[];
};

function statusClass(status: string) {
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "failed") return "border-red-200 bg-red-50 text-red-700";
  if (status === "running") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-zinc-200 bg-zinc-50 text-zinc-600";
}

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 size={16} />;
  if (status === "failed") return <CircleAlert size={16} />;
  if (status === "running") return <PlayCircle size={16} />;
  return <Clock3 size={16} />;
}

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

export function StepOutputPanel({ steps }: StepOutputPanelProps) {
  const [selectedStepId, setSelectedStepId] = useState<number | null>(steps[0]?.step_id ?? null);
  const totalInputTokens = steps.reduce((sum, step) => sum + (step.input_tokens || 0), 0);
  const totalOutputTokens = steps.reduce((sum, step) => sum + (step.output_tokens || 0), 0);
  const selectedStep = useMemo(
    () => steps.find((step) => step.step_id === selectedStepId) ?? steps[0] ?? null,
    [selectedStepId, steps],
  );

  useEffect(() => {
    if (!steps.some((step) => step.step_id === selectedStepId)) {
      setSelectedStepId(steps[0]?.step_id ?? null);
    }
  }, [selectedStepId, steps]);

  if (!steps.length) {
    return <div className="rounded border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-500">暂无生成步骤记录</div>;
  }

  return (
    <div className="grid min-h-[520px] gap-4 lg:grid-cols-[280px_1fr]">
      <div className="overflow-hidden rounded border border-zinc-200 bg-white">
        <div className="border-b border-zinc-200 px-4 py-3">
          <h3 className="text-sm font-semibold text-zinc-900">生成步骤</h3>
          <p className="mt-1 text-xs text-zinc-500">共 {steps.length} 步 · 输入约 {totalInputTokens} · 输出约 {totalOutputTokens}</p>
        </div>
        <div className="max-h-[620px] overflow-auto">
          {steps.map((step, index) => (
            <button
              key={step.step_id}
              onClick={() => setSelectedStepId(step.step_id)}
              className={`flex w-full items-start gap-3 border-b border-zinc-100 px-4 py-3 text-left transition hover:bg-zinc-50 ${
                selectedStep?.step_id === step.step_id ? "bg-zinc-100" : "bg-white"
              }`}
            >
              <span className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${statusClass(step.status)}`}>
                <StatusIcon status={step.status} />
              </span>
              <span className="min-w-0">
                <span className="block text-xs text-zinc-500">步骤 {index + 1}</span>
                <span className="block truncate text-sm font-medium text-zinc-900">{step.step_name}</span>
                <span className="mt-1 block text-xs text-zinc-500">{step.status} · 入 {step.input_tokens || 0} / 出 {step.output_tokens || 0}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="rounded border border-zinc-200 bg-white">
        {selectedStep ? (
          <>
            <div className="border-b border-zinc-200 px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-zinc-950">{selectedStep.step_name}</h3>
                  <p className="mt-1 text-sm text-zinc-500">
                    {formatDate(selectedStep.started_at)} - {formatDate(selectedStep.finished_at)}
                  </p>
                  <p className="mt-1 text-sm text-zinc-500">
                    Token 估算：输入 {selectedStep.input_tokens || 0}，输出 {selectedStep.output_tokens || 0}
                  </p>
                </div>
                <span className={`inline-flex items-center gap-2 rounded border px-3 py-1 text-sm ${statusClass(selectedStep.status)}`}>
                  <StatusIcon status={selectedStep.status} />
                  {selectedStep.status}
                </span>
              </div>
            </div>
            <div className="grid gap-4 p-5">
              {selectedStep.error_message ? (
                <section>
                  <h4 className="mb-2 text-sm font-semibold text-red-700">错误信息</h4>
                  <pre className="max-h-64 overflow-auto rounded bg-red-50 p-4 text-sm leading-6 text-red-800">{selectedStep.error_message}</pre>
                </section>
              ) : null}
              <section>
                <h4 className="mb-2 text-sm font-semibold text-zinc-800">输入预览</h4>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-4 text-sm leading-6 text-zinc-700">
                  {selectedStep.input_preview || "无"}
                </pre>
              </section>
              <section>
                <h4 className="mb-2 text-sm font-semibold text-zinc-800">输出内容</h4>
                <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded bg-zinc-950 p-4 text-sm leading-6 text-zinc-100">
                  {selectedStep.output_content || "无"}
                </pre>
              </section>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
