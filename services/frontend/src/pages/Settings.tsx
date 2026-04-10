import { useState, useEffect, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { WarehouseConfigData } from '../api/client';
import UploadModal from '../components/UploadModal';

const numSort = (a: string, b: string) => {
  const na = parseInt(a, 10);
  const nb = parseInt(b, 10);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  return a.localeCompare(b);
};

const cardStyle: React.CSSProperties = {
  background: '#0d1117',
  border: '1px solid #21262d',
  borderRadius: 12,
  padding: 24,
  marginBottom: 24,
};

const inputStyle: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  color: '#e1e4e8',
  borderRadius: 8,
  padding: '8px 12px',
  fontSize: 13,
  width: '100%',
  boxSizing: 'border-box',
  outline: 'none',
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: '#8b949e',
  marginBottom: 4,
  display: 'block',
  fontWeight: 600,
};

export default function Settings() {
  const [warehouse, setWarehouse] = useState('');
  const [showUpload, setShowUpload] = useState(false);
  const [configForm, setConfigForm] = useState<Partial<WarehouseConfigData>>({});
  const [saved, setSaved] = useState(false);
  const queryClient = useQueryClient();

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => api.getWarehouses(),
  });

  const effectiveWarehouse = warehouse || (warehouses ?? [])[0] || '';

  const { data: config } = useQuery({
    queryKey: ['config', effectiveWarehouse],
    queryFn: () => api.getConfig(effectiveWarehouse),
    enabled: !!effectiveWarehouse,
  });

  useEffect(() => {
    if (config) {
      setConfigForm({
        gazel_capacity: config.gazel_capacity,
        fura_capacity: config.fura_capacity,
        lead_time_min: config.lead_time_min,
        safety_factor: config.safety_factor,
        alpha: config.alpha,
        beta: config.beta,
        travel_buffer_min: config.travel_buffer_min,
        avg_route_duration_min: config.avg_route_duration_min,
      });
      setSaved(false);
    }
  }, [config]);

  const handleSaveConfig = useCallback(async () => {
    if (!effectiveWarehouse) return;
    await api.updateConfig(effectiveWarehouse, configForm);
    queryClient.invalidateQueries({ queryKey: ['config'] });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }, [effectiveWarehouse, configForm, queryClient]);

  const configFields: Array<{
    key: keyof WarehouseConfigData;
    label: string;
    type: 'number' | 'range';
    min?: number;
    max?: number;
    step?: number;
  }> = [
    { key: 'gazel_capacity', label: 'Ёмкость газели', type: 'number', min: 1, step: 0.5 },
    { key: 'fura_capacity', label: 'Ёмкость фуры', type: 'number', min: 1, step: 1 },
    { key: 'lead_time_min', label: 'Lead time (мин)', type: 'number', min: 0 },
    { key: 'safety_factor', label: 'Запас (safety factor)', type: 'range', min: 1.0, max: 1.5, step: 0.01 },
    { key: 'alpha', label: 'Alpha (штраф за нехватку)', type: 'range', min: 0, max: 1, step: 0.05 },
    { key: 'beta', label: 'Beta (штраф за простой)', type: 'range', min: 0, max: 1, step: 0.05 },
    { key: 'travel_buffer_min', label: 'Буфер на дорогу (мин)', type: 'number', min: 0 },
    { key: 'avg_route_duration_min', label: 'Ср. длительность маршрута (мин)', type: 'number', min: 10 },
  ];

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    cursor: 'pointer',
    width: 'auto',
    minWidth: 160,
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e1e4e8', marginBottom: 4 }}>
          Настройки
        </h1>
        <p style={{ color: '#8b949e', fontSize: 14, margin: 0 }}>
          Параметры оптимизатора по складам и загрузка данных
        </p>
      </div>

      {/* Warehouse selector */}
      <div
        style={{
          display: 'flex',
          gap: 12,
          alignItems: 'center',
          padding: '14px 18px',
          background: '#161b22',
          borderRadius: 12,
          border: '1px solid #21262d',
          marginBottom: 20,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, color: '#8b949e', fontWeight: 600, textTransform: 'uppercase' }}>
            Склад
          </label>
          <select
            value={warehouse}
            onChange={(e) => setWarehouse(e.target.value)}
            style={selectStyle}
          >
            {[...(warehouses ?? [])].sort(numSort).map((w) => (
              <option key={w} value={w}>Склад {w}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Config */}
      <div style={cardStyle}>
        <h3 style={{ fontSize: 16, color: '#e1e4e8', fontWeight: 600, marginBottom: 16 }}>
          Параметры оптимизатора
        </h3>
        {config ? (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
              {configFields.map((field) => (
                <div key={field.key}>
                  <label style={labelStyle}>
                    {field.label}
                    {field.type === 'range' && (
                      <span style={{ float: 'right', color: '#58a6ff', fontWeight: 700 }}>
                        {(configForm[field.key] as number)?.toFixed(2) ?? ''}
                      </span>
                    )}
                  </label>
                  {field.type === 'range' ? (
                    <input
                      type="range"
                      min={field.min}
                      max={field.max}
                      step={field.step}
                      value={(configForm[field.key] as number) ?? 0}
                      onChange={(e) =>
                        setConfigForm((prev) => ({ ...prev, [field.key]: parseFloat(e.target.value) }))
                      }
                      style={{ width: '100%', accentColor: '#58a6ff' }}
                    />
                  ) : (
                    <input
                      type="number"
                      min={field.min}
                      step={field.step}
                      value={(configForm[field.key] as number) ?? ''}
                      onChange={(e) =>
                        setConfigForm((prev) => ({ ...prev, [field.key]: parseFloat(e.target.value) }))
                      }
                      style={inputStyle}
                    />
                  )}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 20 }}>
              <button
                onClick={handleSaveConfig}
                style={{
                  background: '#238636',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  padding: '8px 24px',
                  cursor: 'pointer',
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                Сохранить
              </button>
              {saved && <span style={{ color: '#3fb950', fontSize: 13 }}>Сохранено</span>}
            </div>
          </>
        ) : (
          <div style={{ color: '#6e7681' }}>Выберите склад для настройки.</div>
        )}
      </div>

      {/* Upload */}
      <div style={cardStyle}>
        <h3 style={{ fontSize: 16, color: '#e1e4e8', fontWeight: 600, marginBottom: 16 }}>
          Загрузка данных
        </h3>
        <p style={{ color: '#8b949e', fontSize: 13, marginBottom: 16 }}>
          Загрузите файл Parquet с данными маршрутов для обновления прогнозов.
        </p>
        <button
          onClick={() => setShowUpload(true)}
          style={{
            background: '#21262d',
            color: '#e1e4e8',
            border: '1px solid #30363d',
            borderRadius: 8,
            padding: '10px 24px',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          Загрузить Parquet
        </button>
      </div>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onSuccess={() => queryClient.invalidateQueries()}
        />
      )}
    </div>
  );
}
