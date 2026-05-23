import { Upload } from "lucide-react";
import { useRef, useState } from "react";

type FileUploaderProps = {
  busy?: boolean;
  onUpload: (file: File) => Promise<void>;
};

export function FileUploader({ busy = false, onUpload }: FileUploaderProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);

  async function handleFile(file: File | undefined) {
    if (!file || busy) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      throw new Error("请选择 PDF 文件。");
    }
    await onUpload(file);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        void handleFile(event.dataTransfer.files[0]);
      }}
      className={`rounded border border-dashed p-4 transition ${
        dragging ? "border-zinc-950 bg-zinc-100" : "border-zinc-300 bg-zinc-50"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(event) => void handleFile(event.target.files?.[0])}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        className="flex w-full items-center justify-center gap-2 rounded bg-zinc-950 px-3 py-3 text-sm font-medium text-white disabled:opacity-60"
      >
        <Upload size={17} />
        {busy ? "正在上传..." : "上传 PDF"}
      </button>
      <p className="mt-3 text-center text-xs leading-5 text-zinc-500">支持点击选择或拖拽文件。上传后会进入课件列表，再点击解析。</p>
    </div>
  );
}
