import { Loader2, Save, Settings, Wifi } from "lucide-react";
import { useEffect, useState } from "react";

import { getModelConfig, testModelConfig, updateModelConfig } from "../api/client";
import type { ModelConfig } from "../types";

const purposeLabels: Record<string, string> = {
  standard_text: "标准/扩展文字步骤",
  visual_vision: "标准模式插图判断",
  advanced: "高级模式章节生成",
  page_judge: "页面候选图判断",
  review: "报告检查",
  chat: "后续追问",
  advanced_chat: "高级追问",
  quick_text: "预留快速模式",
  visual_text: "预留视觉文字步骤",
};

type Props = {
  open: boolean;
  onClose: () => void;
};

export function ModelSettingsPanel({ open, onClose }: Props) {
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingKey, setTestingKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadConfig() {
    setLoading(true);
    setError(null);
    try {
      setConfig(await getModelConfig());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载模型配置失败");
    } finally {
      setLoading(false);
    }
  }

  async function saveConfig() {
    if (!config) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      setConfig(await updateModelConfig(config));
      setMessage("模型配置已保存，后续生成会使用新配置。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存模型配置失败");
    } finally {
      setSaving(false);
    }
  }

  async function testPurpose(purpose: string) {
    if (!config) return;
    const item = config.purposes[purpose];
    setTestingKey(purpose);
    setError(null);
    setMessage(null);
    try {
      const result = await testModelConfig(item.provider, item.model);
      setMessage(`测试成功：${result.response_preview || "OK"}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "模型测试失败");
    } finally {
      setTestingKey(null);
    }
  }

  useEffect(() => {
    if (open) void loadConfig();
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 bg-black/30 px-4 py-6">
      <div className="mx-auto flex max-h-full max-w-5xl flex-col overflow-hidden rounded border border-zinc-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4">
          <div className="flex items-center gap-3">
            <Settings size={20} />
            <div>
              <h2 className="text-base font-semibold text-zinc-950">模型接口配置</h2>
              <p className="text-sm text-zinc-500">保存后会写入本地 .env，并立即用于后续模型调用。</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded border border-zinc-200 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50">
            关闭
          </button>
        </div>

        <div className="overflow-auto p-5">
          {loading ? <div className="py-10 text-center text-sm text-zinc-500">正在加载配置...</div> : null}
          {error ? <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
          {message ? <div className="mb-4 rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div> : null}

          {config ? (
            <div className="grid gap-5">
              <section>
                <h3 className="mb-3 text-sm font-semibold text-zinc-900">不同步骤使用的模型</h3>
                <div className="grid gap-3">
                  {Object.entries(config.purposes).map(([purpose, item]) => (
                    <div key={purpose} className="grid gap-3 rounded border border-zinc-200 p-3 md:grid-cols-[1.3fr_1fr_1.5fr_auto]">
                      <div>
                        <div className="text-sm font-medium text-zinc-900">{purposeLabels[purpose] ?? purpose}</div>
                        <div className="mt-1 text-xs text-zinc-500">{purpose}</div>
                      </div>
                      <select
                        value={item.provider}
                        onChange={(event) =>
                          setConfig({
                            ...config,
                            purposes: { ...config.purposes, [purpose]: { ...item, provider: event.target.value } },
                          })
                        }
                        className="h-9 rounded border border-zinc-200 bg-white px-2 text-sm"
                      >
                        {config.provider_options.map((provider) => (
                          <option key={provider} value={provider}>{provider}</option>
                        ))}
                      </select>
                      <input
                        value={item.model}
                        onChange={(event) =>
                          setConfig({
                            ...config,
                            purposes: { ...config.purposes, [purpose]: { ...item, model: event.target.value } },
                          })
                        }
                        className="h-9 rounded border border-zinc-200 px-2 text-sm"
                        placeholder="模型名称"
                      />
                      <button
                        onClick={() => void testPurpose(purpose)}
                        disabled={testingKey !== null}
                        className="inline-flex h-9 items-center justify-center gap-2 rounded border border-zinc-200 px-3 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
                      >
                        {testingKey === purpose ? <Loader2 className="animate-spin" size={15} /> : <Wifi size={15} />}
                        测试
                      </button>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h3 className="mb-3 text-sm font-semibold text-zinc-900">供应商 API</h3>
                <div className="grid gap-3 md:grid-cols-2">
                  {Object.entries(config.providers).map(([provider, item]) => (
                    <div key={provider} className="rounded border border-zinc-200 p-3">
                      <div className="mb-3 flex items-center justify-between">
                        <h4 className="text-sm font-semibold text-zinc-900">{provider}</h4>
                        <span className="text-xs text-zinc-500">{item.has_api_key ? "已有 API Key" : "未配置 API Key"}</span>
                      </div>
                      <label className="text-xs text-zinc-500">Base URL</label>
                      <input
                        value={item.base_url}
                        onChange={(event) =>
                          setConfig({
                            ...config,
                            providers: { ...config.providers, [provider]: { ...item, base_url: event.target.value } },
                          })
                        }
                        className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 text-sm"
                      />
                      <label className="mt-3 block text-xs text-zinc-500">API Key</label>
                      <input
                        type="password"
                        value={item.api_key ?? ""}
                        onChange={(event) =>
                          setConfig({
                            ...config,
                            providers: { ...config.providers, [provider]: { ...item, api_key: event.target.value } },
                          })
                        }
                        className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 text-sm"
                        placeholder={item.has_api_key ? "留空则保留现有 Key" : "请输入 API Key"}
                      />
                    </div>
                  ))}
                </div>
              </section>
            </div>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-zinc-200 px-5 py-4">
          <button onClick={onClose} className="rounded border border-zinc-200 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50">
            取消
          </button>
          <button
            onClick={() => void saveConfig()}
            disabled={saving || !config}
            className="inline-flex items-center gap-2 rounded bg-zinc-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
            保存配置
          </button>
        </div>
      </div>
    </div>
  );
}
