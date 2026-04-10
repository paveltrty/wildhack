import { useState, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Order } from '../api/client';

const numSort = (a: string, b: string) => {
  const na = parseInt(a, 10);
  const nb = parseInt(b, 10);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  return a.localeCompare(b);
};

type StatusTab = '' | 'draft' | 'approved' | 'completed';

const TABS: { key: StatusTab; label: string; color: string }[] = [
  { key: '', label: 'Все заявки', color: '#e1e4e8' },
  { key: 'draft', label: 'Черновики', color: '#8b949e' },
  { key: 'approved', label: 'Активные', color: '#58a6ff' },
  { key: 'completed', label: 'Завершённые', color: '#3fb950' },
];

const statusMeta: Record<string, { label: string; color: string; bg: string }> = {
  draft: { label: 'Черновик', color: '#8b949e', bg: 'rgba(139,148,158,0.12)' },
  approved: { label: 'Активная', color: '#58a6ff', bg: 'rgba(88,166,255,0.12)' },
  dispatched: { label: 'В пути', color: '#d29922', bg: 'rgba(210,153,34,0.12)' },
  completed: { label: 'Завершена', color: '#3fb950', bg: 'rgba(63,185,80,0.12)' },
};

function Badge({ status }: { status: string }) {
  const meta = statusMeta[status] ?? { label: status, color: '#6e7681', bg: 'rgba(110,118,129,0.12)' };
  return (
    <span
      style={{
        display: 'inline-block',
        color: meta.color,
        background: meta.bg,
        fontWeight: 600,
        fontSize: 11,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
        padding: '3px 10px',
        borderRadius: 12,
        border: `1px solid ${meta.color}33`,
      }}
    >
      {meta.label}
    </span>
  );
}

function VehicleMix({ fura, gazel }: { fura: number; gazel: number }) {
  const parts: JSX.Element[] = [];
  if (fura > 0) {
    parts.push(
      <span key="fura" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <span style={{ fontSize: 16 }}>🚛</span>
        <span style={{ fontWeight: 600, color: '#f0883e' }}>{fura}</span>
        <span style={{ color: '#8b949e', fontSize: 12 }}>фура</span>
      </span>
    );
  }
  if (gazel > 0) {
    parts.push(
      <span key="gazel" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <span style={{ fontSize: 16 }}>🚐</span>
        <span style={{ fontWeight: 600, color: '#79c0ff' }}>{gazel}</span>
        <span style={{ color: '#8b949e', fontSize: 12 }}>газель</span>
      </span>
    );
  }
  if (parts.length === 0) {
    return <span style={{ color: '#484f58', fontSize: 13 }}>—</span>;
  }
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
      {parts}
    </div>
  );
}

function formatDt(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' }) +
    ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function plural(n: number, one: string, few: string, many: string) {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return many;
  if (last > 1 && last < 5) return few;
  if (last === 1) return one;
  return many;
}

export default function Orders() {
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<StatusTab>('');
  const [warehouseId, setWarehouseId] = useState(searchParams.get('office_from_id') ?? '');
  const [routeId, setRouteId] = useState(searchParams.get('route_id') ?? '');

  // Approve modal state (combines edit + approve)
  const [approveModal, setApproveModal] = useState<Order | null>(null);
  const [editFura, setEditFura] = useState(0);
  const [editGazel, setEditGazel] = useState(0);
  const [editVolume, setEditVolume] = useState('');
  const [editNotes, setEditNotes] = useState('');

  // Complete confirm
  const [completeConfirm, setCompleteConfirm] = useState<Order | null>(null);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const queryClient = useQueryClient();

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => api.getWarehouses(),
  });

  const { data: routes } = useQuery({
    queryKey: ['routes', warehouseId],
    queryFn: () => api.getRoutes(warehouseId || undefined),
  });

  const { data: orders, isLoading } = useQuery({
    queryKey: ['orders', warehouseId, routeId, activeTab],
    queryFn: () =>
      api.getOrders({
        office_from_id: warehouseId || undefined,
        route_id: routeId || undefined,
        status: activeTab || undefined,
      }),
    refetchInterval: 30000,
  });

  const allOrders = orders ?? [];

  const counts = useMemo(() => {
    return {
      '': allOrders.length,
      draft: allOrders.filter((o) => o.status === 'draft').length,
      approved: allOrders.filter((o) => o.status === 'approved' || o.status === 'dispatched').length,
      completed: allOrders.filter((o) => o.status === 'completed').length,
    };
  }, [allOrders]);

  const filteredOrders = useMemo(() => {
    if (activeTab === 'approved') {
      return allOrders.filter((o) => o.status === 'approved' || o.status === 'dispatched');
    }
    return activeTab ? allOrders.filter((o) => o.status === activeTab) : allOrders;
  }, [allOrders, activeTab]);

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['orders'] });
    queryClient.invalidateQueries({ queryKey: ['network'] });
  }, [queryClient]);

  const openApproveModal = useCallback((o: Order) => {
    setApproveModal(o);
    setEditFura(o.fura_count);
    setEditGazel(o.gazel_count);
    setEditVolume(String(o.planned_volume));
    setEditNotes(o.notes || '');
    setError('');
  }, []);

  const handleApprove = useCallback(async () => {
    if (!approveModal) return;
    setSaving(true);
    setError('');
    try {
      await api.approveOrder(approveModal.id, {
        fura_count: editFura,
        gazel_count: editGazel,
        planned_volume: parseFloat(editVolume) || approveModal.y_hat_future,
        notes: editNotes || undefined,
      });
      setApproveModal(null);
      invalidate();
    } catch (e: any) {
      setError(e.message || 'Ошибка при подтверждении');
    } finally {
      setSaving(false);
    }
  }, [approveModal, editFura, editGazel, editVolume, editNotes, invalidate]);

  const handleSaveDraft = useCallback(async () => {
    if (!approveModal) return;
    setSaving(true);
    setError('');
    try {
      await api.updateOrder(approveModal.id, {
        fura_count: editFura,
        gazel_count: editGazel,
        planned_volume: parseFloat(editVolume) || approveModal.y_hat_future,
        notes: editNotes || undefined,
      });
      setApproveModal(null);
      invalidate();
    } catch (e: any) {
      setError(e.message || 'Ошибка при сохранении');
    } finally {
      setSaving(false);
    }
  }, [approveModal, editFura, editGazel, editVolume, editNotes, invalidate]);

  const handleComplete = useCallback(async () => {
    if (!completeConfirm) return;
    setSaving(true);
    try {
      await api.completeOrder(completeConfirm.id);
      setCompleteConfirm(null);
      invalidate();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  }, [completeConfirm, invalidate]);

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

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    cursor: 'pointer',
    width: 'auto',
    minWidth: 160,
  };

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e1e4e8', marginBottom: 4 }}>
          Заявки на перевозку
        </h1>
        <p style={{ color: '#8b949e', fontSize: 14, margin: 0 }}>
          Модель предсказывает объём и предлагает транспорт. Проверьте черновик, скорректируйте и подтвердите.
        </p>
      </div>

      {/* Filters */}
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
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, color: '#8b949e', fontWeight: 600, textTransform: 'uppercase' }}>
            Склад
          </label>
          <select
            value={warehouseId}
            onChange={(e) => { setWarehouseId(e.target.value); setRouteId(''); }}
            style={selectStyle}
          >
            <option value="">Все склады</option>
            {[...(warehouses ?? [])].sort(numSort).map((w) => (
              <option key={w} value={w}>Склад {w}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, color: '#8b949e', fontWeight: 600, textTransform: 'uppercase' }}>
            Маршрут
          </label>
          <select value={routeId} onChange={(e) => setRouteId(e.target.value)} style={selectStyle}>
            <option value="">Все маршруты</option>
            {[...(routes ?? [])].sort((a, b) => numSort(a.route_id, b.route_id)).map((r) => (
              <option key={r.route_id} value={r.route_id}>
                Маршрут {r.route_id}
              </option>
            ))}
          </select>
        </div>

        <div style={{ flex: 1 }} />

        <div style={{ color: '#484f58', fontSize: 13 }}>
          {filteredOrders.length} {plural(filteredOrders.length, 'заявка', 'заявки', 'заявок')}
        </div>
      </div>

      {/* Status tabs */}
      <div
        style={{
          display: 'flex',
          gap: 2,
          marginBottom: 20,
          background: '#0d1117',
          borderRadius: 10,
          padding: 3,
          border: '1px solid #21262d',
          width: 'fit-content',
        }}
      >
        {TABS.map((tab) => {
          const isActive = activeTab === tab.key;
          const count = counts[tab.key] ?? 0;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                background: isActive ? '#21262d' : 'transparent',
                color: isActive ? tab.color : '#484f58',
                border: 'none',
                borderRadius: 8,
                padding: '8px 18px',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              {tab.label}
              <span
                style={{
                  background: isActive ? `${tab.color}22` : 'transparent',
                  color: isActive ? tab.color : '#484f58',
                  fontSize: 11,
                  fontWeight: 700,
                  padding: '1px 7px',
                  borderRadius: 10,
                  minWidth: 20,
                  textAlign: 'center',
                }}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Orders list */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#484f58' }}>Загрузка...</div>
      ) : filteredOrders.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: 60,
            color: '#484f58',
            background: '#0d1117',
            borderRadius: 12,
            border: '1px solid #21262d',
          }}
        >
          <div style={{ fontSize: 40, marginBottom: 12, opacity: 0.4 }}>📦</div>
          <div style={{ fontSize: 15, fontWeight: 500 }}>Заявок не найдено</div>
          <div style={{ fontSize: 13, marginTop: 4 }}>Измените фильтры или дождитесь новых предсказаний модели</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filteredOrders.map((o) => (
            <OrderCard
              key={o.id}
              order={o}
              onApprove={() => openApproveModal(o)}
              onComplete={() => setCompleteConfirm(o)}
            />
          ))}
        </div>
      )}

      {/* ─── Approve / Edit Modal ─────────────────────── */}
      {approveModal && (
        <Modal onClose={() => setApproveModal(null)}>
          <h3 style={{ color: '#e1e4e8', marginBottom: 4, fontSize: 18 }}>
            Подтверждение заявки
          </h3>
          <p style={{ color: '#8b949e', fontSize: 13, marginBottom: 20 }}>
            Маршрут <strong style={{ color: '#c9d1d9' }}>{approveModal.route_id}</strong> · Склад <strong style={{ color: '#c9d1d9' }}>{approveModal.office_from_id}</strong> · Отправка {formatDt(approveModal.scheduled_departure)}
          </p>

          {/* Prediction info */}
          <div style={{ marginBottom: 20, padding: 14, background: '#0d1117', borderRadius: 10, border: '1px solid #21262d' }}>
            <div style={{ fontSize: 11, color: '#8b949e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 10 }}>
              Предсказание модели
            </div>
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
              <div>
                <div style={{ color: '#484f58', fontSize: 11 }}>Прогноз объёма</div>
                <div style={{ color: '#d2a8ff', fontWeight: 700, fontSize: 20 }}>{approveModal.y_hat_future.toFixed(1)}</div>
              </div>
              <div>
                <div style={{ color: '#484f58', fontSize: 11 }}>Горизонт</div>
                <div style={{ color: '#f0883e', fontWeight: 700, fontSize: 20 }}>h{approveModal.chosen_horizon}</div>
              </div>
              <div>
                <div style={{ color: '#484f58', fontSize: 11 }}>Score</div>
                <div style={{ color: '#79c0ff', fontWeight: 700, fontSize: 20 }}>{approveModal.optimizer_score.toFixed(3)}</div>
              </div>
              <div>
                <div style={{ color: '#484f58', fontSize: 11 }}>Ёмкость ТС</div>
                <div style={{ color: '#8b949e', fontWeight: 700, fontSize: 20 }}>{approveModal.capacity_units.toFixed(1)}</div>
              </div>
            </div>
          </div>

          {/* Editable fields */}
          <div style={{ fontSize: 11, color: '#8b949e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 10 }}>
            Скорректируйте при необходимости
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 13, color: '#c9d1d9', marginBottom: 6, fontWeight: 600 }}>
                🚛 Фуры
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  onClick={() => setEditFura(Math.max(0, editFura - 1))}
                  style={counterBtn}
                >−</button>
                <input
                  type="number"
                  min="0"
                  value={editFura}
                  onChange={(e) => setEditFura(Math.max(0, parseInt(e.target.value) || 0))}
                  style={{ ...inputStyle, textAlign: 'center', flex: 1 }}
                />
                <button
                  onClick={() => setEditFura(editFura + 1)}
                  style={counterBtn}
                >+</button>
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 13, color: '#c9d1d9', marginBottom: 6, fontWeight: 600 }}>
                🚐 Газели
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  onClick={() => setEditGazel(Math.max(0, editGazel - 1))}
                  style={counterBtn}
                >−</button>
                <input
                  type="number"
                  min="0"
                  value={editGazel}
                  onChange={(e) => setEditGazel(Math.max(0, parseInt(e.target.value) || 0))}
                  style={{ ...inputStyle, textAlign: 'center', flex: 1 }}
                />
                <button
                  onClick={() => setEditGazel(editGazel + 1)}
                  style={counterBtn}
                >+</button>
              </div>
            </div>
          </div>

          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', fontSize: 13, color: '#c9d1d9', marginBottom: 6, fontWeight: 600 }}>
              Фактический отправляемый объём
            </label>
            <input
              type="number"
              step="0.1"
              value={editVolume}
              onChange={(e) => setEditVolume(e.target.value)}
              style={inputStyle}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 13, color: '#c9d1d9', marginBottom: 6, fontWeight: 600 }}>
              Заметки
            </label>
            <textarea
              value={editNotes}
              onChange={(e) => setEditNotes(e.target.value)}
              placeholder="Комментарий к заявке..."
              rows={2}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </div>

          {error && (
            <div style={{ color: '#f85149', fontSize: 13, marginBottom: 14, padding: '8px 12px', background: 'rgba(248,81,73,0.1)', borderRadius: 8, border: '1px solid rgba(248,81,73,0.3)' }}>
              {error}
            </div>
          )}

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button onClick={() => setApproveModal(null)} style={btnSecondary}>
              Отмена
            </button>
            <button onClick={handleSaveDraft} disabled={saving} style={btnOutline}>
              Сохранить черновик
            </button>
            <button
              onClick={handleApprove}
              disabled={saving || (editFura === 0 && editGazel === 0)}
              style={{
                ...btnPrimary,
                opacity: (saving || (editFura === 0 && editGazel === 0)) ? 0.5 : 1,
              }}
            >
              {saving ? 'Подтверждение...' : 'Подтвердить и активировать'}
            </button>
          </div>
        </Modal>
      )}

      {/* ─── Complete Confirm ─────────────────────────── */}
      {completeConfirm && (
        <Modal onClose={() => setCompleteConfirm(null)}>
          <h3 style={{ color: '#e1e4e8', marginBottom: 12, fontSize: 18 }}>
            Завершить заявку?
          </h3>
          <div style={{ marginBottom: 20, padding: 16, background: '#0d1117', borderRadius: 10, border: '1px solid #21262d' }}>
            <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginBottom: 12 }}>
              <div>
                <div style={{ color: '#484f58', fontSize: 11, marginBottom: 2 }}>Маршрут</div>
                <div style={{ color: '#e1e4e8', fontWeight: 600, fontSize: 16 }}>{completeConfirm.route_id}</div>
              </div>
              <div>
                <div style={{ color: '#484f58', fontSize: 11, marginBottom: 2 }}>Склад</div>
                <div style={{ color: '#e1e4e8', fontWeight: 600, fontSize: 16 }}>{completeConfirm.office_from_id}</div>
              </div>
              <div>
                <div style={{ color: '#484f58', fontSize: 11, marginBottom: 2 }}>Объём</div>
                <div style={{ color: '#79c0ff', fontWeight: 600, fontSize: 16 }}>{completeConfirm.planned_volume.toFixed(1)}</div>
              </div>
            </div>
            <VehicleMix fura={completeConfirm.fura_count} gazel={completeConfirm.gazel_count} />
          </div>

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button onClick={() => setCompleteConfirm(null)} style={btnSecondary}>
              Отмена
            </button>
            <button onClick={handleComplete} disabled={saving} style={btnPrimary}>
              {saving ? 'Завершение...' : 'Завершить'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ─── Order Card ──────────────────────────────────────── */

function OrderCard({
  order: o,
  onApprove,
  onComplete,
}: {
  order: Order;
  onApprove: () => void;
  onComplete: () => void;
}) {
  const isDraft = o.status === 'draft';
  const isActive = o.status === 'approved' || o.status === 'dispatched';

  return (
    <div
      style={{
        background: '#0d1117',
        border: `1px solid ${isDraft ? '#30363d' : isActive ? '#1f6feb33' : '#23863633'}`,
        borderRadius: 12,
        padding: '16px 20px',
        transition: 'border-color 0.15s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        {/* Left: route + warehouse */}
        <div style={{ flex: '1 1 200px', minWidth: 180 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 16, fontWeight: 700, color: '#e1e4e8' }}>
              Маршрут {o.route_id}
            </span>
            <Badge status={o.status} />
          </div>
          <div style={{ display: 'flex', gap: 16, fontSize: 13, color: '#8b949e', flexWrap: 'wrap' }}>
            <span>Склад <strong style={{ color: '#c9d1d9' }}>{o.office_from_id}</strong></span>
            <span>Отправка <strong style={{ color: '#c9d1d9' }}>{formatDt(o.scheduled_departure)}</strong></span>
          </div>
        </div>

        {/* Center: vehicle mix */}
        <div
          style={{
            flex: '0 0 auto',
            padding: '10px 18px',
            background: '#161b22',
            borderRadius: 10,
            border: '1px solid #21262d',
          }}
        >
          <div style={{ fontSize: 10, color: '#484f58', fontWeight: 600, textTransform: 'uppercase', marginBottom: 6 }}>
            Транспорт
          </div>
          <VehicleMix fura={o.fura_count} gazel={o.gazel_count} />
        </div>

        {/* Right: metrics */}
        <div style={{ flex: '0 0 auto', display: 'flex', gap: 16, alignItems: 'center' }}>
          <MetricBox label="Прогноз" value={o.y_hat_future.toFixed(1)} color="#d2a8ff" />
          <MetricBox label="Объём" value={o.planned_volume.toFixed(1)} color="#79c0ff" />
          <MetricBox label="Ёмкость" value={o.capacity_units.toFixed(1)} color="#8b949e" />
          <MetricBox label="h*" value={String(o.chosen_horizon)} color="#f0883e" />
        </div>

        {/* Actions */}
        <div style={{ flex: '0 0 auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          {isDraft && (
            <button onClick={onApprove} style={btnPrimary}>
              Рассмотреть
            </button>
          )}
          {isActive && (
            <button onClick={onComplete} style={btnBlue}>
              Завершить
            </button>
          )}
        </div>
      </div>

      {o.notes && (
        <div
          style={{
            marginTop: 10,
            padding: '8px 12px',
            background: '#161b22',
            borderRadius: 8,
            fontSize: 13,
            color: '#8b949e',
            borderLeft: '3px solid #30363d',
          }}
        >
          {o.notes}
        </div>
      )}
    </div>
  );
}

/* ─── Small Components ────────────────────────────────── */

function MetricBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ textAlign: 'center', minWidth: 52 }}>
      <div style={{ fontSize: 10, color: '#484f58', fontWeight: 600, textTransform: 'uppercase', marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}

function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.65)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 300,
        backdropFilter: 'blur(4px)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#161b22',
          border: '1px solid #30363d',
          borderRadius: 14,
          padding: 28,
          width: 520,
          maxWidth: '95vw',
          maxHeight: '90vh',
          overflowY: 'auto',
          boxShadow: '0 16px 48px rgba(0,0,0,0.4)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

/* ─── Styles ──────────────────────────────────────────── */

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

const btnBlue: React.CSSProperties = {
  background: '#1f6feb',
  color: '#fff',
  border: 'none',
  borderRadius: 8,
  padding: '8px 18px',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 600,
};

const btnOutline: React.CSSProperties = {
  background: 'transparent',
  color: '#c9d1d9',
  border: '1px solid #30363d',
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
