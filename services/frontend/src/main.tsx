import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Orders from "./pages/Orders";
import Analytics from "./pages/Analytics";
import Fleet from "./pages/Fleet";
import Settings from "./pages/Settings";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

const navItems = [
  { to: "/orders", label: "Orders" },
  { to: "/analytics", label: "Analytics" },
  { to: "/fleet", label: "Fleet" },
  { to: "/settings", label: "Settings" },
];

function App() {
  return (
    <div style={{ fontFamily: "'Inter', sans-serif", background: "#f5f7fa", minHeight: "100vh" }}>
      <nav
        style={{
          display: "flex",
          alignItems: "center",
          gap: 24,
          padding: "0 32px",
          height: 56,
          background: "#1e293b",
          color: "#fff",
          fontSize: 14,
          fontWeight: 500,
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 16, marginRight: 24 }}>Transport Dispatch</span>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            style={({ isActive }) => ({
              color: isActive ? "#38bdf8" : "#94a3b8",
              textDecoration: "none",
              padding: "6px 12px",
              borderRadius: 6,
              background: isActive ? "rgba(56,189,248,0.1)" : "transparent",
            })}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main style={{ padding: 32, maxWidth: 1280, margin: "0 auto" }}>
        <Routes>
          <Route path="/" element={<Orders />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/fleet" element={<Fleet />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
