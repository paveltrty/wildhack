const API_BASE = import.meta.env.VITE_API_URL || "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export interface Order {
  id: string;
  warehouse_id: string;
  scheduled_departure: string;
  vehicle_type: string;
  vehicle_count: number;
  capacity_units: number;
  chosen_horizon: number;
  optimizer_score: number;
  status: string;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Vehicle {
  id: string;
  warehouse_id: string;
  vehicle_type: string;
  status: string;
  route_id: string | null;
  dispatched_at: string | null;
  eta_return: string | null;
  updated_at: string | null;
}

export interface Forecast {
  id: string;
  run_ts: string;
  office_from_id: string;
  horizon: number;
  minutes_ahead: number;
  y_hat: number;
  confidence: number;
  y_hat_low: number | null;
  y_hat_high: number | null;
}

export interface WarehouseConfig {
  warehouse_id: string;
  gazel_capacity: number;
  fura_capacity: number;
  lead_time_min: number;
  safety_factor: number;
  alpha: number;
  beta: number;
  travel_buffer_min: number;
  updated_at: string | null;
}

export interface BusinessMetrics {
  fleet_utilization_rate: number;
  miss_rate: number;
  idle_vehicle_rate: number;
  return_eta_error_min: number;
  lead_time_adherence: number;
  total_orders: number;
}

export interface ScoreDecision {
  optimal_horizon: number;
  optimal_score: number;
  scores_by_horizon: Record<string, number>;
  vehicles_needed: number;
  extra_needed: number;
  scheduled_departure: string;
  y_hat: number;
  available_capacity: number;
}

export const api = {
  getOrders: (params: { warehouse_id?: string; date?: string; status?: string }) => {
    const qs = new URLSearchParams();
    if (params.warehouse_id) qs.set("warehouse_id", params.warehouse_id);
    if (params.date) qs.set("date", params.date);
    if (params.status) qs.set("status", params.status);
    return request<Order[]>(`/orders?${qs}`);
  },

  approveOrder: (id: string) =>
    request<{ id: string; status: string }>(`/orders/${id}/approve`, { method: "POST" }),

  completeOrder: (id: string, actual_shipments: number) =>
    request<{ id: string; status: string }>(`/orders/${id}/complete`, {
      method: "POST",
      body: JSON.stringify({ actual_shipments }),
    }),

  getVehicles: (warehouse_id?: string) => {
    const qs = warehouse_id ? `?warehouse_id=${warehouse_id}` : "";
    return request<Vehicle[]>(`/vehicles${qs}`);
  },

  createVehicle: (warehouse_id: string, vehicle_type: string) =>
    request<Vehicle>("/vehicles", {
      method: "POST",
      body: JSON.stringify({ warehouse_id, vehicle_type }),
    }),

  dispatchVehicle: (id: string, route_id: string) =>
    request(`/vehicles/${id}/dispatch`, {
      method: "POST",
      body: JSON.stringify({ route_id }),
    }),

  returnVehicle: (id: string) =>
    request(`/vehicles/${id}/return`, { method: "POST" }),

  getForecasts: (warehouse_id: string, from_ts?: string, to_ts?: string) => {
    const qs = new URLSearchParams({ warehouse_id });
    if (from_ts) qs.set("from_ts", from_ts);
    if (to_ts) qs.set("to_ts", to_ts);
    return request<{ forecasts: Forecast[]; optimizer_scores: ScoreDecision | null }>(
      `/forecasts?${qs}`
    );
  },

  getMetrics: (warehouse_id: string, period_days = 7) =>
    request<{ metrics: BusinessMetrics }>(`/analytics/metrics?warehouse_id=${warehouse_id}&period_days=${period_days}`),

  getScoreProfile: (warehouse_id: string) =>
    request<{ decisions: ScoreDecision[] }>(`/analytics/score-profile?warehouse_id=${warehouse_id}`),

  getConfig: (warehouse_id: string) =>
    request<WarehouseConfig>(`/config/${warehouse_id}`),

  updateConfig: (warehouse_id: string, data: Partial<WarehouseConfig>) =>
    request<WarehouseConfig>(`/config/${warehouse_id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  uploadFile: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
    if (!res.ok) throw new Error("Upload failed");
    return res.json();
  },

  getHealth: () => request<{ status: string; checks: Record<string, unknown> }>("/health"),
};
