import { useState, useRef, useCallback } from 'react';
import { api } from '../api/client';

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.7)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 300,
};

const modalStyle: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 12,
  padding: 32,
  width: 480,
  maxWidth: '90vw',
};

const dropZoneStyle: React.CSSProperties = {
  border: '2px dashed #30363d',
  borderRadius: 8,
  padding: 40,
  textAlign: 'center',
  color: '#8b949e',
  cursor: 'pointer',
  transition: 'border-color 0.2s',
};

export default function UploadModal({ onClose, onSuccess }: Props) {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ rows_inserted: number; actuals_inserted: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setResult(null);
    setUploading(true);
    try {
      const res = await api.uploadFile(file);
      setResult(res);
      onSuccess();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }, [onSuccess]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ color: '#e1e4e8', fontSize: 18, fontWeight: 700, marginBottom: 20 }}>Upload Data</h2>

        <div
          style={{ ...dropZoneStyle, borderColor: dragOver ? '#58a6ff' : '#30363d' }}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".parquet"
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
          {uploading ? (
            <span style={{ color: '#58a6ff' }}>Uploading...</span>
          ) : (
            <>
              <div style={{ fontSize: 14, marginBottom: 8 }}>
                Drop .parquet file here or click to browse
              </div>
              <div style={{ fontSize: 12, color: '#6e7681' }}>
                Requires: route_id, office_from_id, timestamp, status_1..8
              </div>
            </>
          )}
        </div>

        {result && (
          <div style={{ marginTop: 16, padding: 14, background: '#0d1117', borderRadius: 8, border: '1px solid #238636' }}>
            <div style={{ color: '#3fb950', fontWeight: 600, marginBottom: 6 }}>Upload successful</div>
            <div style={{ color: '#8b949e', fontSize: 13 }}>
              Rows: {result.rows_inserted} · Actuals: {result.actuals_inserted}
            </div>
          </div>
        )}

        {error && (
          <div style={{ marginTop: 16, padding: 14, background: '#0d1117', borderRadius: 8, border: '1px solid #f85149' }}>
            <div style={{ color: '#f85149', fontSize: 13 }}>{error}</div>
          </div>
        )}

        <div style={{ marginTop: 20, textAlign: 'right' }}>
          <button
            onClick={onClose}
            style={{
              background: '#21262d',
              color: '#e1e4e8',
              border: '1px solid #30363d',
              borderRadius: 6,
              padding: '8px 20px',
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
