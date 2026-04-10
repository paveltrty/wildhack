import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import NetworkGraph, { extractWarehouseNum } from '../components/NetworkGraph';
import RoutePanel from '../components/RoutePanel';

const LEGEND: Array<{
  shape: 'rect' | 'circle';
  color: string;
  label: string;
}> = [
  { shape: 'rect', color: '#4c8bf5', label: 'Склад' },
  { shape: 'circle', color: '#6e7681', label: 'Маршрут (нет груза)' },
  { shape: 'circle', color: '#58a6ff', label: 'Маршрут (мало)' },
  { shape: 'circle', color: '#d29922', label: 'Маршрут (средний)' },
  { shape: 'circle', color: '#f85149', label: 'Маршрут (много)' },
];

export default function Network() {
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);
  const [focusWarehouse, setFocusWarehouse] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState({ width: 900, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  const { data } = useQuery({
    queryKey: ['network'],
    queryFn: api.getNetwork,
    refetchInterval: 30000,
  });

  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setDimensions({
          width: Math.max(600, rect.width),
          height: Math.max(400, window.innerHeight - 260),
        });
      }
    };
    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, []);

  const warehouses = (data?.nodes ?? [])
    .filter((n) => n.type === 'warehouse')
    .sort((a, b) => extractWarehouseNum(a) - extractWarehouseNum(b));

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 10,
        }}
      >
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Сеть складов</h1>
        <div style={{ fontSize: 12, color: '#6e7681' }}>
          Авто-обновление 30с &middot;{' '}
          {data ? `${data.nodes.length} узлов` : 'Загрузка\u2026'}
        </div>
      </div>

      {/* Legend */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '5px 14px',
          marginBottom: 10,
          padding: '7px 12px',
          background: '#161b22',
          borderRadius: 8,
          border: '1px solid #21262d',
          fontSize: 12,
          color: '#8b949e',
          alignItems: 'center',
        }}
      >
        {LEGEND.map((item) => (
          <span
            key={item.label}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}
          >
            <span
              style={{
                display: 'inline-block',
                width: item.shape === 'rect' ? 14 : 10,
                height: item.shape === 'rect' ? 10 : 10,
                borderRadius: item.shape === 'rect' ? 3 : '50%',
                background: item.color,
              }}
            />
            {item.label}
          </span>
        ))}

        <span
          style={{
            marginLeft: 'auto',
            paddingLeft: 12,
            borderLeft: '1px solid #30363d',
            color: '#6e7681',
            fontSize: 11,
          }}
        >
          Скролл: зум &middot; Тяни фон: панорама &middot; Тяни узел:
          перетащить &middot; Клик склад: фильтр &middot; Клик маршрут:
          детали &middot; 2&times;клик: сброс
        </span>
      </div>

      {/* Warehouse navigation */}
      {warehouses.length > 0 && (
        <div
          style={{
            display: 'flex',
            gap: 6,
            overflowX: 'auto',
            padding: '8px 12px',
            background: '#161b22',
            borderRadius: 8,
            border: '1px solid #21262d',
            marginBottom: 10,
          }}
        >
          <button
            onClick={() => setFocusWarehouse(null)}
            style={{
              padding: '5px 14px',
              borderRadius: 6,
              border:
                focusWarehouse === null
                  ? '1px solid #4c8bf5'
                  : '1px solid #30363d',
              background:
                focusWarehouse === null
                  ? 'rgba(76,139,245,0.15)'
                  : 'transparent',
              color: focusWarehouse === null ? '#4c8bf5' : '#8b949e',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: focusWarehouse === null ? 600 : 400,
              whiteSpace: 'nowrap',
              transition: 'all 0.15s',
            }}
          >
            Все склады
          </button>
          {warehouses.map((w) => {
            const active = focusWarehouse === w.id;
            const label = (w.label ?? w.id).replace(
              /^Warehouse\s*/i,
              'WH ',
            );
            return (
              <button
                key={w.id}
                onClick={() => setFocusWarehouse(active ? null : w.id)}
                style={{
                  padding: '5px 14px',
                  borderRadius: 6,
                  border: active
                    ? '1px solid #4c8bf5'
                    : '1px solid #30363d',
                  background: active
                    ? 'rgba(76,139,245,0.15)'
                    : 'transparent',
                  color: active ? '#4c8bf5' : '#8b949e',
                  cursor: 'pointer',
                  fontSize: 12,
                  fontWeight: active ? 600 : 400,
                  whiteSpace: 'nowrap',
                  transition: 'all 0.15s',
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      <div ref={containerRef} style={{ position: 'relative' }}>
        {data && (
          <NetworkGraph
            nodes={data.nodes}
            edges={data.edges}
            width={selectedRoute ? dimensions.width - 440 : dimensions.width}
            height={dimensions.height}
            onRouteClick={(id) => {
              setSelectedRoute(id);
              const route = data?.nodes.find((n) => n.id === id);
              if (route?.office_from_id) {
                setFocusWarehouse(route.office_from_id);
              }
            }}
            focusWarehouseId={focusWarehouse}
          />
        )}
      </div>

      {selectedRoute && (
        <RoutePanel
          routeId={selectedRoute}
          onClose={() => setSelectedRoute(null)}
        />
      )}
    </div>
  );
}
