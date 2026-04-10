import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { FleetSummary } from '../api/client';

const numSort = (a: string, b: string) => {
  const na = parseInt(a, 10);
  const nb = parseInt(b, 10);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  return a.localeCompare(b);
};

export default function Vehicles() {
  const queryClient = useQueryClient();
  const [editWarehouse, setEditWarehouse] = useState<FleetSummary | null>(null);
  const [editGazel, setEditGazel] = useState(0);
  const [editFura, setEditFura] = useState(0);
  const [saving, setSaving] = useState(false);
  const [filterWh, setFilterWh] = useState('');

  const { data: fleet, isLoading } = useQuery({
    queryKey: ['fleet-summary'],
    queryFn: () => api.getFleetSummary(),
    refetchInterval: 15000,
  });

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => api.getWarehouses(),
  });

  const displayed = (fleet ?? []).filter(
    (w) => !filterWh || w.warehouse_id === filterWh
  );

  const totals = (fleet ?? []).reduce(
    (acc, w) => ({
      gazel_total: acc.gazel_total + w.gazel_total,
      gazel_free: acc.gazel_free + w.gazel_free,
      gazel_busy: acc.gazel_busy + w.gazel_busy,
      fura_total: acc.fura_total + w.fura_total,
      fura_free: acc.fura_free + w.fura_free,
      fura_busy: acc.fura_busy + w.fura_busy,
    }),
    { gazel_total: 0, gazel_free: 0, gazel_busy: 0, fura_total: 0, fura_free: 0, fura_busy: 0 }
  );

  const openEdit = useCallback((w: FleetSummary) => {
    setEditWarehouse(w);
    setEditGazel(w.gazel_total);
    setEditFura(w.fura_total);
  }, []);

  const handleSave = useCallback(async () => {
    if (!editWarehouse) return;
    setSaving(true);
    try {
      await api.setFleet(editWarehouse.warehouse_id, editGazel, editFura);
      setEditWarehouse(null);
      queryClient.invalidateQueries({ queryKey: ['fleet-summary'] });
      queryClient.invalidateQueries({ queryKey: ['network'] });
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  }, [editWarehouse, editGazel, editFura, queryClient]);

  const selectStyle: React.CSSProperties = {
    background: '#0d1117',
    border: '1px solid #30363d',
    color: '#e1e4e8',
    borderRadius: 8,
    padding: '8px 14px',
    fontSize: 14,
    cursor: 'pointer',
    minWidth: 160,
  };

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e1e4e8', marginBottom: 4 }}>
          Парк транспортных средств
        </h1>
        <p style={{ color: '#8b949e', fontSize: 14, margin: 0 }}>
          Управление составом парка по складам. Быстрое добавление и удаление машин.
        </p>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 24 }}>
        <SummaryCard icon="🚐" label="Газели всего" value={totals.gazel_total} color="#79c0ff" />
        <SummaryCard icon="🚐" label="Газели свободны" value={totals.gazel_free} color="#3fb950" />
        <SummaryCard icon="🚛" label="Фуры всего" value={totals.fura_total} color="#f0883e" />
        <SummaryCard icon="🚛" label="Фуры свободны" value={totals.fura_free} color="#3fb950" />
      </div>

      {/* Filter */}
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
          <select value={filterWh} onChange={(e) => setFilterWh(e.target.value)} style={selectStyle}>
            <option value="">Все склады</option>
            {[...(warehouses ?? [])].sort(numSort).map((w) => (
              <option key={w} value={w}>Склад {w}</option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ color: '#484f58', fontSize: 13 }}>
          {displayed.length} {displayed.length === 1 ? 'склад' : displayed.length < 5 ? 'склада' : 'складов'}
        </div>
      </div>

      {/* Fleet table */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#484f58' }}>Загрузка...</div>
      ) : displayed.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#484f58', background: '#0d1117', borderRadius: 12, border: '1px solid #21262d' }}>
          <div style={{ fontSize: 40, marginBottom: 12, opacity: 0.4 }}>🚛</div>
          <div style={{ fontSize: 15, fontWeight: 500 }}>Нет данных о парке</div>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Склад', '🚐 Газели', '', '', '🚛 Фуры', '', '', ''].map((col, i) => (
                  <th key={i} style={thStyle}>
                    {i === 0 ? col : i === 1 ? 'Газели всего' : i === 2 ? 'Свободно' : i === 3 ? 'Занято' : i === 4 ? 'Фуры всего' : i === 5 ? 'Свободно' : i === 6 ? 'Занято' : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayed.map((w) => (
                <tr key={w.warehouse_id} style={{ background: '#0d1117' }}>
                  <td style={tdStyle}>
                    <span style={{ fontWeight: 600, color: '#58a6ff' }}>Склад {w.warehouse_id}</span>
                  </td>
                  <td style={tdStyle}>
                    <span style={{ fontWeight: 700, color: '#79c0ff', fontSize: 16 }}>{w.gazel_total}</span>
                  </td>
                  <td style={tdStyle}>
                    <span style={{ color: '#3fb950' }}>{w.gazel_free}</span>
                  </td>
                  <td style={tdStyle}>
                    <span style={{ color: w.gazel_busy > 0 ? '#d29922' : '#484f58' }}>{w.gazel_busy}</span>
                  </td>
                  <td style={tdStyle}>
                    <span style={{ fontWeight: 700, color: '#f0883e', fontSize: 16 }}>{w.fura_total}</span>
                  </td>
                  <td style={tdStyle}>
                    <span style={{ color: '#3fb950' }}>{w.fura_free}</span>
                  </td>
                  <td style={tdStyle}>
                    <span style={{ color: w.fura_busy > 0 ? '#d29922' : '#484f58' }}>{w.fura_busy}</span>
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    <button onClick={() => openEdit(w)} style={btnEdit}>
                      Изменить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Edit modal */}
      {editWarehouse && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 300, backdropFilter: 'blur(4px)' }}
          onClick={() => setEditWarehouse(null)}
        >
          <div
            style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 14, padding: 28, width: 460, maxWidth: '95vw', boxShadow: '0 16px 48px rgba(0,0,0,0.4)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ color: '#e1e4e8', marginBottom: 4, fontSize: 18 }}>
              Парк — Склад {editWarehouse.warehouse_id}
            </h3>
            <p style={{ color: '#8b949e', fontSize: 13, marginBottom: 20 }}>
              Установите желаемое количество. Занятые машины не удаляются.
            </p>

            {/* Current state */}
            <div style={{ marginBottom: 20, padding: 14, background: '#0d1117', borderRadius: 10, border: '1px solid #21262d' }}>
              <div style={{ fontSize: 11, color: '#8b949e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 10 }}>
                Текущее состояние
              </div>
              <div style={{ display: 'flex', gap: 24 }}>
                <div>
                  <div style={{ color: '#484f58', fontSize: 11 }}>🚐 Газели</div>
                  <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
                    <span style={{ color: '#3fb950', fontWeight: 600 }}>{editWarehouse.gazel_free} своб.</span>
                    <span style={{ color: '#d29922', fontWeight: 600 }}>{editWarehouse.gazel_busy} зан.</span>
                  </div>
                </div>
                <div>
                  <div style={{ color: '#484f58', fontSize: 11 }}>🚛 Фуры</div>
                  <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
                    <span style={{ color: '#3fb950', fontWeight: 600 }}>{editWarehouse.fura_free} своб.</span>
                    <span style={{ color: '#d29922', fontWeight: 600 }}>{editWarehouse.fura_busy} зан.</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Editable counts */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, color: '#c9d1d9', marginBottom: 6, fontWeight: 600 }}>
                  🚐 Газели (всего)
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button onClick={() => setEditGazel(Math.max(editWarehouse.gazel_busy, editGazel - 1))} style={counterBtn}>−</button>
                  <input
                    type="number"
                    min={editWarehouse.gazel_busy}
                    value={editGazel}
                    onChange={(e) => setEditGazel(Math.max(editWarehouse.gazel_busy, parseInt(e.target.value) || 0))}
                    style={{ ...inputStyle, textAlign: 'center', flex: 1 }}
                  />
                  <button onClick={() => setEditGazel(editGazel + 1)} style={counterBtn}>+</button>
                </div>
                {editGazel < editWarehouse.gazel_busy && (
                  <div style={{ color: '#f85149', fontSize: 11, marginTop: 4 }}>
                    Мин. {editWarehouse.gazel_busy} (заняты)
                  </div>
                )}
                {editGazel !== editWarehouse.gazel_total && (
                  <div style={{ color: '#8b949e', fontSize: 11, marginTop: 4 }}>
                    {editGazel > editWarehouse.gazel_total
                      ? `+${editGazel - editWarehouse.gazel_total}`
                      : `${editGazel - editWarehouse.gazel_total}`}
                  </div>
                )}
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, color: '#c9d1d9', marginBottom: 6, fontWeight: 600 }}>
                  🚛 Фуры (всего)
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button onClick={() => setEditFura(Math.max(editWarehouse.fura_busy, editFura - 1))} style={counterBtn}>−</button>
                  <input
                    type="number"
                    min={editWarehouse.fura_busy}
                    value={editFura}
                    onChange={(e) => setEditFura(Math.max(editWarehouse.fura_busy, parseInt(e.target.value) || 0))}
                    style={{ ...inputStyle, textAlign: 'center', flex: 1 }}
                  />
                  <button onClick={() => setEditFura(editFura + 1)} style={counterBtn}>+</button>
                </div>
                {editFura < editWarehouse.fura_busy && (
                  <div style={{ color: '#f85149', fontSize: 11, marginTop: 4 }}>
                    Мин. {editWarehouse.fura_busy} (заняты)
                  </div>
                )}
                {editFura !== editWarehouse.fura_total && (
                  <div style={{ color: '#8b949e', fontSize: 11, marginTop: 4 }}>
                    {editFura > editWarehouse.fura_total
                      ? `+${editFura - editWarehouse.fura_total}`
                      : `${editFura - editWarehouse.fura_total}`}
                  </div>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setEditWarehouse(null)} style={btnSecondary}>Отмена</button>
              <button onClick={handleSave} disabled={saving} style={btnPrimary}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ icon, label, value, color }: { icon: string; label: string; value: number; color: string }) {
  return (
    <div style={{ background: '#0d1117', border: '1px solid #21262d', borderRadius: 12, padding: '16px 20px' }}>
      <div style={{ fontSize: 12, color: '#8b949e', marginBottom: 6 }}>{icon} {label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '10px 14px',
  fontSize: 11,
  color: '#8b949e',
  fontWeight: 600,
  textTransform: 'uppercase',
  borderBottom: '1px solid #21262d',
  background: '#161b22',
};

const tdStyle: React.CSSProperties = {
  padding: '12px 14px',
  fontSize: 14,
  borderBottom: '1px solid #161b22',
  color: '#e1e4e8',
};

const inputStyle: React.CSSProperties = {
  background: '#0d1117',
  border: '1px solid #30363d',
  color: '#e1e4e8',
  borderRadius: 8,
  padding: '8px 14px',
  fontSize: 14,
  outline: 'none',
  width: '100%',
  boxSizing: 'border-box',
};

const counterBtn: React.CSSProperties = {
  background: '#21262d',
  color: '#e1e4e8',
  border: '1px solid #30363d',
  borderRadius: 6,
  width: 32,
  height: 34,
  cursor: 'pointer',
  fontSize: 16,
  fontWeight: 600,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
};

const btnPrimary: React.CSSProperties = {
  background: '#238636',
  color: '#fff',
  border: 'none',
  borderRadius: 8,
  padding: '8px 18px',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 600,
};

const btnSecondary: React.CSSProperties = {
  background: '#21262d',
  color: '#e1e4e8',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: '8px 18px',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 500,
};

const btnEdit: React.CSSProperties = {
  background: 'transparent',
  color: '#58a6ff',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: '6px 14px',
  cursor: 'pointer',
  fontSize: 12,
  fontWeight: 600,
};
