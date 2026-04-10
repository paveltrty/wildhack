import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, ComposedChart, Cell, PieChart, Pie, AreaChart, Area,
} from 'recharts';
import { api } from '../api/client';

type Tab = 'system' | 'warehouses' | 'routes';

const COLORS = {
  bg: '#0d1117',
  card: '#161b22',
  border: '#21262d',
  borderLight: '#30363d',
  text: '#e1e4e8',
  textMuted: '#8b949e',
  textDim: '#6e7681',
  blue: '#58a6ff',
  green: '#3fb950',
  yellow: '#d29922',
  red: '#f85149',
  purple: '#bc8cff',
  orange: '#f0883e',
  cyan: '#39d2c0',
};

const cardStyle: React.CSSProperties = {
  background: COLORS.card,
  border: `1px solid ${COLORS.border}`,
  borderRadius: 12,
  padding: 24,
};

const tooltipStyle = {
  background: '#1c2128',
  border: `1px solid ${COLORS.borderLight}`,
  borderRadius: 6,
  color: COLORS.text,
};

const selectStyle: React.CSSProperties = {
  background: COLORS.bg,
  border: `1px solid ${COLORS.borderLight}`,
  color: COLORS.text,
  borderRadius: 6,
  padding: '6px 12px',
  fontSize: 13,
};

function MetricCard({ label, value, sub, color }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div style={{
      background: COLORS.bg,
      borderRadius: 10,
      padding: '18px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      border: `1px solid ${COLORS.border}`,
    }}>
      <div style={{ color: COLORS.textMuted, fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        {label}
      </div>
      <div style={{ color: color || COLORS.text, fontSize: 24, fontWeight: 700, lineHeight: 1.2 }}>
        {value}
      </div>
      {sub && <div style={{ color: COLORS.textDim, fontSize: 11 }}>{sub}</div>}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 16, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
      {children}
    </h3>
  );
}

function pct(v: number) { return `${(v * 100).toFixed(1)}%`; }
function num(v: number) { return v.toFixed(1); }

/** Сортировка идентификаторов складов/маршрутов как чисел, если строка — целое число. */
function idSortKey(id: string): [number, number, string] {
  const n = parseInt(id, 10);
  if (!Number.isNaN(n) && String(n) === id) return [0, n, id];
  return [1, 0, id];
}

function sortIds(ids: string[]): string[] {
  return [...ids].sort((a, b) => {
    const ka = idSortKey(a);
    const kb = idSortKey(b);
    if (ka[0] !== kb[0]) return ka[0] - kb[0];
    if (ka[0] === 0) return ka[1] - kb[1];
    return ka[2].localeCompare(kb[2]);
  });
}

function SystemTab({ period }: { period: number }) {
  const { data: sys, isLoading } = useQuery({
    queryKey: ['systemMetrics', period],
    queryFn: () => api.getSystemMetrics(period),
  });

  if (isLoading) return <div style={{ color: COLORS.textDim, padding: 40 }}>Загрузка...</div>;
  if (!sys) return <div style={{ color: COLORS.textDim, padding: 40 }}>Нет данных</div>;

  const statusData = [
    { name: 'Завершено', value: sys.orders_completed, color: COLORS.green },
    { name: 'Утверждено', value: sys.orders_approved, color: COLORS.blue },
    { name: 'Черновик', value: sys.orders_draft, color: COLORS.yellow },
    { name: 'Прочее', value: Math.max(0, sys.orders_total - sys.orders_completed - sys.orders_approved - sys.orders_draft), color: COLORS.textDim },
  ].filter(d => d.value > 0);

  const maeCompareData = [
    { name: 'Прогноз черновика', value: sys.forecast_mae, fill: COLORS.blue },
    { name: 'Naive baseline', value: sys.naive_mae, fill: COLORS.red },
  ];

  const whData = [...sys.warehouse_breakdown].sort((a, b) => {
    const c = idSortKey(a.warehouse_id);
    const d = idSortKey(b.warehouse_id);
    if (c[0] !== d[0]) return c[0] - d[0];
    if (c[0] === 0) return c[1] - d[1];
    return c[2].localeCompare(d[2]);
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        <MetricCard label="Всего заявок" value={String(sys.orders_total)} sub={`за ${sys.period_days} дн.`} />
        <MetricCard label="Завершено" value={String(sys.orders_completed)} color={COLORS.green}
          sub={sys.orders_total > 0 ? `${pct(sys.orders_completed / sys.orders_total)} от всех` : ''} />
        <MetricCard label="Утилизация машин" value={pct(sys.fleet_utilization_rate)} color={sys.fleet_utilization_rate > 0.7 ? COLORS.green : COLORS.yellow} />
        <MetricCard label="Miss Rate" value={pct(sys.miss_rate)} color={sys.miss_rate > 0.1 ? COLORS.red : COLORS.green} />
        <MetricCard label="Idle Rate" value={pct(sys.idle_vehicle_rate)} color={sys.idle_vehicle_rate > 0.3 ? COLORS.orange : COLORS.green} />
        <MetricCard label="Сред. объём отгр." value={num(sys.avg_actual_shipments)} sub="ед. на заявку" />
        <MetricCard label="MAE прогноза" value={num(sys.forecast_mae)} sub="черновик vs факт" color={COLORS.purple} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <div style={cardStyle}>
          <SectionTitle>Заявки по дням</SectionTitle>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={sys.orders_by_day}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
              <XAxis dataKey="date" tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
              <YAxis tick={{ fill: COLORS.textMuted, fontSize: 11 }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Area type="monotone" dataKey="total" stroke={COLORS.blue} fill={COLORS.blue} fillOpacity={0.15} name="Всего" strokeWidth={2} />
              <Area type="monotone" dataKey="completed" stroke={COLORS.green} fill={COLORS.green} fillOpacity={0.15} name="Завершено" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div style={cardStyle}>
          <SectionTitle>Статусы заявок</SectionTitle>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <ResponsiveContainer width="60%" height={240}>
              <PieChart>
                <Pie
                  data={statusData}
                  cx="50%" cy="50%"
                  innerRadius={55} outerRadius={85}
                  dataKey="value"
                  paddingAngle={3}
                  stroke="none"
                >
                  {statusData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
              </PieChart>
            </ResponsiveContainer>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '40%' }}>
              {statusData.map(d => (
                <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 10, height: 10, borderRadius: 2, background: d.color, flexShrink: 0 }} />
                  <span style={{ color: COLORS.textMuted, fontSize: 12 }}>{d.name}</span>
                  <span style={{ color: COLORS.text, fontSize: 13, fontWeight: 600, marginLeft: 'auto' }}>{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={cardStyle}>
        <SectionTitle>Точность прогноза: предложение в черновике vs факт при завершении</SectionTitle>
        <p style={{ color: COLORS.textDim, fontSize: 12, marginTop: -8, marginBottom: 16 }}>
          Среднее |ŷ из черновика − фактическая отгрузка| по завершённым заявкам за период (тот же горизонт, что выбрал оптимизатор, заложен в поле заявки).
        </p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={maeCompareData}>
            <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
            <XAxis dataKey="name" tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
            <YAxis tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
            <Tooltip contentStyle={tooltipStyle} />
            <Bar dataKey="value" radius={[6, 6, 0, 0]} barSize={48}>
              {maeCompareData.map((e, i) => (
                <Cell key={i} fill={e.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {whData.length > 0 && (
        <div style={cardStyle}>
          <SectionTitle>Показатели по складам</SectionTitle>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  {['Склад', 'Заявок', 'Завершено', 'Утилизация', 'Объём отгрузок'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: COLORS.textMuted, fontWeight: 600, fontSize: 11, textTransform: 'uppercase' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {whData.map(wh => (
                  <tr key={wh.warehouse_id} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                    <td style={{ padding: '10px 12px', color: COLORS.blue, fontWeight: 600 }}>{wh.warehouse_id}</td>
                    <td style={{ padding: '10px 12px', color: COLORS.text }}>{wh.orders_total}</td>
                    <td style={{ padding: '10px 12px', color: COLORS.green }}>{wh.orders_completed}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 60, height: 6, background: COLORS.bg, borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{ width: `${Math.min(100, wh.utilization_rate * 100)}%`, height: '100%', background: wh.utilization_rate > 0.7 ? COLORS.green : COLORS.yellow, borderRadius: 3 }} />
                        </div>
                        <span style={{ color: COLORS.text, fontSize: 12 }}>{pct(wh.utilization_rate)}</span>
                      </div>
                    </td>
                    <td style={{ padding: '10px 12px', color: COLORS.text }}>{num(wh.total_shipments)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function WarehousesTab({ period }: { period: number }) {
  const [warehouse, setWarehouse] = useState('');

  const { data: networkData } = useQuery({ queryKey: ['network'], queryFn: api.getNetwork });
  const warehouseIds = sortIds(
    (networkData?.nodes ?? []).filter(n => n.type === 'warehouse').map(n => n.id),
  );
  const effectiveWarehouse = warehouse || warehouseIds[0] || '';

  const { data: metrics } = useQuery({
    queryKey: ['metrics', effectiveWarehouse, period],
    queryFn: () => api.getMetrics(effectiveWarehouse, period),
    enabled: !!effectiveWarehouse,
  });

  const maeCompareData = metrics
    ? [
        { name: 'Прогноз черновика', value: metrics.forecast_mae, fill: COLORS.blue },
        { name: 'Naive baseline', value: metrics.naive_mae, fill: COLORS.red },
      ]
    : [];

  const completionRate = metrics && metrics.orders_total > 0
    ? metrics.orders_completed / metrics.orders_total
    : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <label style={{ color: COLORS.textMuted, fontSize: 13 }}>Склад:</label>
        <select
          value={effectiveWarehouse}
          onChange={e => setWarehouse(e.target.value)}
          style={{ ...selectStyle, minWidth: 160 }}
        >
          {warehouseIds.map(id => (
            <option key={id} value={id}>Склад {id}</option>
          ))}
        </select>
      </div>

      {!metrics ? (
        <div style={{ color: COLORS.textDim, padding: 40 }}>Выберите склад для просмотра метрик</div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            <MetricCard label="Утилизация машин" value={pct(metrics.fleet_utilization_rate)}
              color={metrics.fleet_utilization_rate > 0.7 ? COLORS.green : COLORS.yellow} />
            <MetricCard label="Miss Rate" value={pct(metrics.miss_rate)}
              color={metrics.miss_rate > 0.1 ? COLORS.red : COLORS.green}
              sub="факт > ёмкости" />
            <MetricCard label="Idle Rate" value={pct(metrics.idle_vehicle_rate)}
              color={metrics.idle_vehicle_rate > 0.3 ? COLORS.orange : COLORS.green}
              sub="факт < 50% ёмкости" />
            <MetricCard label="Завершено / Всего" value={`${metrics.orders_completed} / ${metrics.orders_total}`}
              color={COLORS.text} sub={pct(completionRate)} />
            <MetricCard label="MAE прогноза" value={num(metrics.forecast_mae)} sub="черновик vs факт" color={COLORS.purple} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            <div style={cardStyle}>
              <SectionTitle>Утилизация и покрытие</SectionTitle>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={[
                  { name: 'Утилизация', value: metrics.fleet_utilization_rate * 100, fill: COLORS.blue },
                  { name: 'Miss', value: metrics.miss_rate * 100, fill: COLORS.red },
                  { name: 'Idle', value: metrics.idle_vehicle_rate * 100, fill: COLORS.orange },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                  <YAxis tick={{ fill: COLORS.textMuted, fontSize: 11 }} unit="%" />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => `${v.toFixed(1)}%`} />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                    {[COLORS.blue, COLORS.red, COLORS.orange].map((c, i) => (
                      <Cell key={i} fill={c} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div style={cardStyle}>
              <SectionTitle>Прогноз черновика vs факт</SectionTitle>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={maeCompareData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="name" tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                  <YAxis tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]} barSize={40}>
                    {maeCompareData.map((e, i) => (
                      <Cell key={i} fill={e.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function RoutesTab({ period }: { period: number }) {
  const [routeId, setRouteId] = useState('');

  const { data: routesSummary } = useQuery({
    queryKey: ['routesSummary', period],
    queryFn: () => api.getRoutesSummary(period),
  });

  const { data: networkData } = useQuery({ queryKey: ['network'], queryFn: api.getNetwork });
  const routeIds = sortIds(
    (networkData?.nodes ?? []).filter(n => n.type === 'route').map(n => n.id),
  );
  const effectiveRoute = routeId || routeIds[0] || '';

  const { data: routeMetrics } = useQuery({
    queryKey: ['routeMetrics', effectiveRoute, period],
    queryFn: () => api.getRouteMetrics(effectiveRoute, period),
    enabled: !!effectiveRoute,
  });

  const { data: scoreProfiles } = useQuery({
    queryKey: ['scoreProfile', effectiveRoute],
    queryFn: () => api.getScoreProfile(effectiveRoute),
    enabled: !!effectiveRoute,
  });

  const { data: forecasts } = useQuery({
    queryKey: ['forecasts', effectiveRoute],
    queryFn: () => api.getForecasts({ route_id: effectiveRoute }),
    enabled: !!effectiveRoute,
  });

  const latestProfile = scoreProfiles?.[0];
  const chosenHorizon = latestProfile?.chosen_horizon;

  const scoreData = forecasts
    ? Array.from({ length: 10 }, (_, i) => {
        const h = i + 1;
        const f = forecasts.find(r => r.horizon === h);
        return {
          horizon: `h${h}`,
          score: f?.y_hat_future ?? 0,
          confidence: f?.confidence ?? 0,
          isChosen: h === chosenHorizon,
        };
      })
    : [];

  const routeMaeCompare = routeMetrics
    ? [{ name: 'Прогноз черновика', value: routeMetrics.forecast_mae, fill: COLORS.purple }]
    : [];

  const sortedRoutesSummary = routesSummary
    ? [...routesSummary].sort((a, b) => {
        const c = idSortKey(a.route_id);
        const d = idSortKey(b.route_id);
        if (c[0] !== d[0]) return c[0] - d[0];
        if (c[0] === 0) return c[1] - d[1];
        return c[2].localeCompare(d[2]);
      })
    : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <label style={{ color: COLORS.textMuted, fontSize: 13 }}>Маршрут:</label>
        <select
          value={effectiveRoute}
          onChange={e => setRouteId(e.target.value)}
          style={{ ...selectStyle, minWidth: 160 }}
        >
          {routeIds.map(id => (
            <option key={id} value={id}>Маршрут {id}</option>
          ))}
        </select>
      </div>

      {sortedRoutesSummary.length > 0 && (
        <div style={cardStyle}>
          <SectionTitle>Сводка по маршрутам</SectionTitle>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  {['Маршрут', 'Склад', 'Длит. (мин)', 'Заявок', 'Завершено', 'Ср. отгрузка'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: COLORS.textMuted, fontWeight: 600, fontSize: 11, textTransform: 'uppercase' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRoutesSummary.map(r => (
                  <tr
                    key={r.route_id}
                    onClick={() => setRouteId(r.route_id)}
                    style={{
                      borderBottom: `1px solid ${COLORS.border}`,
                      cursor: 'pointer',
                      background: r.route_id === effectiveRoute ? `${COLORS.blue}11` : 'transparent',
                    }}
                  >
                    <td style={{ padding: '10px 12px', color: r.route_id === effectiveRoute ? COLORS.blue : COLORS.text, fontWeight: r.route_id === effectiveRoute ? 600 : 400 }}>
                      {r.route_id}
                    </td>
                    <td style={{ padding: '10px 12px', color: COLORS.textMuted }}>{r.office_from_id}</td>
                    <td style={{ padding: '10px 12px', color: COLORS.text }}>{num(r.avg_duration_min)}</td>
                    <td style={{ padding: '10px 12px', color: COLORS.text }}>{r.orders_total}</td>
                    <td style={{ padding: '10px 12px', color: COLORS.green }}>{r.orders_completed}</td>
                    <td style={{ padding: '10px 12px', color: COLORS.text }}>{num(r.avg_shipments)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {routeMetrics && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            <MetricCard label="Заявок" value={String(routeMetrics.orders_total)} />
            <MetricCard label="Завершено" value={String(routeMetrics.orders_completed)} color={COLORS.green} />
            <MetricCard label="Утилизация" value={pct(routeMetrics.utilization_rate)}
              color={routeMetrics.utilization_rate > 0.7 ? COLORS.green : COLORS.yellow} />
            <MetricCard label="Ср. план" value={num(routeMetrics.avg_planned_volume)} sub="ед." />
            <MetricCard label="Ср. факт" value={num(routeMetrics.avg_actual_shipments)} sub="ед." color={COLORS.cyan} />
            <MetricCard label="Ср. ёмкость" value={num(routeMetrics.avg_capacity_units)} sub="ед." />
            <MetricCard label="MAE прогноза" value={num(routeMetrics.forecast_mae)} sub="черновик vs факт" color={COLORS.purple} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            <div style={cardStyle}>
              <SectionTitle>История отгрузок</SectionTitle>
              {routeMetrics.shipments_history.length > 0 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={routeMetrics.shipments_history.map(h => ({
                    time: h.window_start ? new Date(h.window_start).toLocaleDateString('ru', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '?',
                    shipments: h.shipments,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                    <XAxis dataKey="time" tick={{ fill: COLORS.textMuted, fontSize: 10 }} angle={-30} textAnchor="end" height={50} />
                    <YAxis tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Area type="monotone" dataKey="shipments" stroke={COLORS.cyan} fill={COLORS.cyan} fillOpacity={0.15} name="Отгрузки" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ color: COLORS.textDim, padding: 20 }}>Нет данных об отгрузках</div>
              )}
            </div>

            <div style={cardStyle}>
              <SectionTitle>Прогноз черновика vs факт</SectionTitle>
              {routeMetrics.orders_completed > 0 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={routeMaeCompare}>
                    <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                    <XAxis dataKey="name" tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                    <YAxis tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="value" radius={[6, 6, 0, 0]} barSize={56}>
                      {routeMaeCompare.map((e, i) => (
                        <Cell key={i} fill={e.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ color: COLORS.textDim, padding: 20 }}>Нет завершённых заявок с фактом за период</div>
              )}
            </div>
          </div>
        </>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <div style={cardStyle}>
          <SectionTitle>Score Profile — {effectiveRoute}</SectionTitle>
          {scoreData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={scoreData}>
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                <XAxis dataKey="horizon" tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fill: COLORS.textMuted, fontSize: 11 }} domain={[0, 1]} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend />
                <Bar yAxisId="left" dataKey="score" name="Score" barSize={20} radius={[4, 4, 0, 0]}>
                  {scoreData.map((entry, idx) => (
                    <Cell key={idx} fill={entry.isChosen ? COLORS.yellow : COLORS.blue} />
                  ))}
                </Bar>
                <Line yAxisId="right" type="monotone" dataKey="confidence" stroke={COLORS.green} name="Confidence" dot={false} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: COLORS.textDim, padding: 20 }}>Нет данных профиля</div>
          )}
        </div>

        <div style={cardStyle}>
          <SectionTitle>Прогноз по горизонтам — {effectiveRoute}</SectionTitle>
          {forecasts && forecasts.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={forecasts.map(f => ({
                horizon: `h${f.horizon}`,
                y_hat_future: f.y_hat_future,
                y_hat_raw: f.y_hat_raw,
                y_hat_low: f.y_hat_low,
                y_hat_high: f.y_hat_high,
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                <XAxis dataKey="horizon" tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                <YAxis tick={{ fill: COLORS.textMuted, fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend />
                <Line type="monotone" dataKey="y_hat_future" stroke={COLORS.blue} name="Future (30мин)" strokeWidth={2} />
                <Line type="monotone" dataKey="y_hat_raw" stroke={COLORS.textMuted} name="Raw (2ч)" strokeDasharray="4 2" />
                <Line type="monotone" dataKey="y_hat_low" stroke={COLORS.textDim} name="Low CI" strokeDasharray="2 2" />
                <Line type="monotone" dataKey="y_hat_high" stroke={COLORS.textDim} name="High CI" strokeDasharray="2 2" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: COLORS.textDim, padding: 20 }}>Нет данных прогноза</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Analytics() {
  const [tab, setTab] = useState<Tab>('system');
  const [period, setPeriod] = useState(7);

  const tabs: { key: Tab; label: string }[] = [
    { key: 'system', label: 'Система' },
    { key: 'warehouses', label: 'Склады' },
    { key: 'routes', label: 'Маршруты' },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: COLORS.text }}>Аналитика</h1>
        <select value={period} onChange={e => setPeriod(Number(e.target.value))} style={selectStyle}>
          <option value={7}>7 дней</option>
          <option value={14}>14 дней</option>
          <option value={30}>30 дней</option>
        </select>
      </div>

      <div style={{
        display: 'flex',
        gap: 0,
        marginBottom: 24,
        borderBottom: `1px solid ${COLORS.border}`,
      }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '12px 24px',
              background: 'none',
              border: 'none',
              borderBottom: `2px solid ${tab === t.key ? COLORS.blue : 'transparent'}`,
              color: tab === t.key ? COLORS.blue : COLORS.textMuted,
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'system' && <SystemTab period={period} />}
      {tab === 'warehouses' && <WarehousesTab period={period} />}
      {tab === 'routes' && <RoutesTab period={period} />}
    </div>
  );
}
