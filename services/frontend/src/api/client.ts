const API_BASE = import.meta.env.VITE_API_URL || '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`API ${resp.status}: ${text}`);
  }
  return resp.json() as Promise<T>;
}

export interface NetworkNode {
  id: string;
  type: 'warehouse' | 'route';
  label?: string;
  office_from_id?: string;
  free_gazel?: number;
  busy_gazel?: number;
  free_fura?: number;
  busy_fura?: number;
  avg_duration_min?: number;
  latest_y_hat_future?: number;
  latest_horizon?: number;
  latest_confidence?: number;
  active_orders?: number;
  urgency?: 'none' | 'low' | 'medium' | 'high';
  trucks?: Array<{ type: string; count: number }>;
}

export interface NetworkEdge {
  source: string;
  target: string;
  has_pending_orders: boolean;
}

export interface NetworkData {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
}

export interface ForecastRow {
  id: string;
  route_id: string;
  office_from_id: string;
  run_ts: string;
  horizon: number;
  y_hat_raw: number;
  y_hat_future: number;
  confidence: number;
  y_hat_low: number | null;
  y_hat_high: number | null;
}

export interface Order {
  id: string;
  route_id: string;
  office_from_id: string;
  scheduled_departure: string;
  fura_count: number;
  gazel_count: number;
  vehicle_type: string | null;
  vehicle_count: number | null;
  capacity_units: number;
  planned_volume: number;
  chosen_horizon: number;
  optimizer_score: number;
  y_hat_future: number;
  status: string;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RouteInfo {
  route_id: string;
  office_from_id: string;
}

export interface Vehicle {
  id: string;
  warehouse_id: string;
  vehicle_type: string;
  status: string;
  dispatched_at: string | null;
  eta_return: string | null;
  updated_at: string | null;
}

export interface FleetSummary {
  warehouse_id: string;
  gazel_free: number;
  gazel_busy: number;
  gazel_total: number;
  fura_free: number;
  fura_busy: number;
  fura_total: number;
}

export interface WarehouseConfigData {
  warehouse_id: string;
  gazel_capacity: number;
  fura_capacity: number;
  lead_time_min: number;
  safety_factor: number;
  alpha: number;
  beta: number;
  travel_buffer_min: number;
  avg_route_duration_min: number;
  updated_at: string | null;
}

export interface BusinessMetrics {
  warehouse_id: string;
  period_days: number;
  fleet_utilization_rate: number;
  miss_rate: number;
  idle_vehicle_rate: number;
  return_eta_error_min: number;
  forecast_mae: number;
  naive_mae: number;
  orders_total: number;
  orders_completed: number;
}

export interface SystemMetrics {
  period_days: number;
  orders_total: number;
  orders_completed: number;
  orders_approved: number;
  orders_draft: number;
  fleet_utilization_rate: number;
  miss_rate: number;
  idle_vehicle_rate: number;
  total_shipments: number;
  total_capacity: number;
  avg_planned_volume: number;
  avg_actual_shipments: number;
  warehouse_breakdown: Array<{
    warehouse_id: string;
    orders_total: number;
    orders_completed: number;
    utilization_rate: number;
    total_shipments: number;
  }>;
  orders_by_day: Array<{
    date: string;
    total: number;
    completed: number;
  }>;
  forecast_mae: number;
  naive_mae: number;
}

export interface RouteMetrics {
  route_id: string;
  office_from_id: string;
  period_days: number;
  orders_total: number;
  orders_completed: number;
  avg_planned_volume: number;
  avg_actual_shipments: number;
  avg_capacity_units: number;
  utilization_rate: number;
  miss_rate: number;
  idle_rate: number;
  forecast_mae: number;
  shipments_history: Array<{
    window_start: string | null;
    shipments: number;
  }>;
}

export interface RouteSummary {
  route_id: string;
  office_from_id: string;
  avg_duration_min: number;
  orders_total: number;
  orders_completed: number;
  avg_shipments: number;
}

export interface ScoreProfile {
  order_id: string;
  created_at: string | null;
  chosen_horizon: number;
  optimizer_score: number;
  y_hat_future: number;
  scores_by_horizon: Record<string, { y_hat_future: number; confidence: number }>;
}

export const api = {
  getNetwork: () => request<NetworkData>('/network'),

  getForecasts: (params: { route_id?: string; office_from_id?: string }) => {
    const qs = new URLSearchParams();
    if (params.route_id) qs.set('route_id', params.route_id);
    if (params.office_from_id) qs.set('office_from_id', params.office_from_id);
    return request<ForecastRow[]>(`/forecasts?${qs}`);
  },

  getOrders: (params: { office_from_id?: string; route_id?: string; status?: string }) => {
    const qs = new URLSearchParams();
    if (params.office_from_id) qs.set('office_from_id', params.office_from_id);
    if (params.route_id) qs.set('route_id', params.route_id);
    if (params.status) qs.set('status', params.status);
    return request<Order[]>(`/orders?${qs}`);
  },

  getWarehouses: () => request<string[]>('/orders/warehouses'),

  getRoutes: (office_from_id?: string) => {
    const qs = office_from_id ? `?office_from_id=${office_from_id}` : '';
    return request<RouteInfo[]>(`/orders/routes${qs}`);
  },

  updateOrder: (id: string, data: {
    fura_count?: number;
    gazel_count?: number;
    planned_volume?: number;
    notes?: string;
  }) =>
    request<Order>(`/orders/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  approveOrder: (id: string, data?: {
    fura_count?: number;
    gazel_count?: number;
    planned_volume?: number;
    notes?: string;
  }) =>
    request<Order>(`/orders/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify(data ?? {}),
    }),

  completeOrder: (id: string) =>
    request<Order>(`/orders/${id}/complete`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  getVehicles: (warehouse_id?: string) => {
    const qs = warehouse_id ? `?warehouse_id=${warehouse_id}` : '';
    return request<Vehicle[]>(`/vehicles${qs}`);
  },

  getFleetSummary: () => request<FleetSummary[]>('/vehicles/summary'),

  createVehicles: (warehouse_id: string, vehicle_type: string, count: number) =>
    request<{ created: number }>('/vehicles', {
      method: 'POST',
      body: JSON.stringify({ warehouse_id, vehicle_type, count }),
    }),

  setFleet: (warehouse_id: string, gazel_count: number, fura_count: number) =>
    request<{ warehouse_id: string }>('/vehicles/set-fleet', {
      method: 'POST',
      body: JSON.stringify({ warehouse_id, gazel_count, fura_count }),
    }),

  returnVehicle: (id: string) =>
    request<{ status: string }>(`/vehicles/${id}/return`, { method: 'POST' }),

  getConfig: (warehouse_id: string) =>
    request<WarehouseConfigData>(`/config/${warehouse_id}`),

  updateConfig: (warehouse_id: string, data: Partial<WarehouseConfigData>) =>
    request<{ status: string }>(`/config/${warehouse_id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  getMetrics: (warehouse_id: string, period_days: number) =>
    request<BusinessMetrics>(`/analytics/metrics?warehouse_id=${warehouse_id}&period_days=${period_days}`),

  getSystemMetrics: (period_days: number) =>
    request<SystemMetrics>(`/analytics/system?period_days=${period_days}`),

  getRouteMetrics: (route_id: string, period_days: number) =>
    request<RouteMetrics>(`/analytics/route-metrics?route_id=${route_id}&period_days=${period_days}`),

  getRoutesSummary: (period_days: number) =>
    request<RouteSummary[]>(`/analytics/routes-summary?period_days=${period_days}`),

  getScoreProfile: (route_id: string) =>
    request<ScoreProfile[]>(`/analytics/score-profile?route_id=${route_id}`),

  uploadFile: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
    if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
    return resp.json() as Promise<{
      rows_inserted: number;
      actuals_inserted: number;
      warehouses: string[];
      routes: string[];
    }>;
  },
};
