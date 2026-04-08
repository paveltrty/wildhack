import { useState, useCallback } from "react";
import { api } from "../api/client";

interface Props {
  onClose: () => void;
}

export default function UploadModal({ onClose }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<{ rows_inserted: number; warehouses: string[]; routes: string[] } | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith(".parquet")) {
      setFile(f);
      setError("");
    } else {
      setError("Please drop a .parquet file");
    }
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const res = await api.uploadFile(file);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700 }}>Upload Parquet Data</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer" }}>
            &times;
          </button>
        </div>

        {!result ? (
          <>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              style={{
                border: `2px dashed ${dragging ? "#3b82f6" : "#cbd5e1"}`,
                borderRadius: 12,
                padding: 40,
                textAlign: "center",
                cursor: "pointer",
                background: dragging ? "#eff6ff" : "#f8fafc",
                transition: "all 0.2s",
              }}
              onClick={() => {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = ".parquet";
                input.onchange = (e) => {
                  const f = (e.target as HTMLInputElement).files?.[0];
                  if (f) { setFile(f); setError(""); }
                };
                input.click();
              }}
            >
              {file ? (
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#1e293b" }}>{file.name}</div>
                  <div style={{ fontSize: 12, color: "#64748b" }}>{(file.size / 1024 / 1024).toFixed(1)} MB</div>
                </div>
              ) : (
                <div style={{ color: "#64748b", fontSize: 14 }}>
                  Drag & drop a .parquet file here, or click to browse
                </div>
              )}
            </div>

            {error && <p style={{ color: "#ef4444", fontSize: 13, marginTop: 8 }}>{error}</p>}

            <button
              onClick={handleUpload}
              disabled={!file || uploading}
              style={{
                marginTop: 16,
                padding: "10px 24px",
                background: file ? "#3b82f6" : "#94a3b8",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                cursor: file ? "pointer" : "default",
                fontSize: 14,
                fontWeight: 600,
                width: "100%",
              }}
            >
              {uploading ? "Uploading..." : "Upload"}
            </button>
          </>
        ) : (
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 48, marginBottom: 8, color: "#22c55e" }}>&#10003;</div>
            <p style={{ fontWeight: 600, marginBottom: 8 }}>Upload Successful</p>
            <p style={{ fontSize: 13, color: "#64748b" }}>
              {result.rows_inserted} rows inserted across {result.warehouses.length} warehouses
              and {result.routes.length} routes.
            </p>
            <button onClick={onClose} style={{ marginTop: 16, padding: "8px 20px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600 }}>
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.4)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: 16,
  padding: 28,
  minWidth: 400,
  maxWidth: 500,
  boxShadow: "0 12px 48px rgba(0,0,0,0.2)",
};
