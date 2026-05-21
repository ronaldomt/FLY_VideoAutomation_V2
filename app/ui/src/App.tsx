import { NavLink, Route, Routes } from "react-router-dom";
import { Menu } from "lucide-react";
import { useState } from "react";
import { IdlePage } from "@/pages/idle/IdlePage";
import { SessionPage } from "@/pages/session/SessionPage";
import { SettingsPage } from "@/pages/settings/SettingsPage";
import { SetupPage } from "@/pages/setup/SetupPage";
import { LogsPage } from "@/pages/logs/LogsPage";

export function App() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-slate-800 px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold tracking-tight">FLY Video Automation</span>
          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300">v0.1</span>
        </div>
        <div className="relative">
          <button
            type="button"
            className="rounded-md p-2 hover:bg-slate-800"
            onClick={() => setMenuOpen((o) => !o)}
            aria-label="Open menu"
          >
            <Menu size={18} />
          </button>
          {menuOpen ? (
            <nav
              className="absolute right-0 mt-1 w-44 rounded-md border border-slate-700 bg-slate-900 py-1 text-sm shadow-xl"
              onClick={() => setMenuOpen(false)}
            >
              <MenuItem to="/">Idle</MenuItem>
              <MenuItem to="/settings">Settings</MenuItem>
              <MenuItem to="/setup">First-run setup</MenuItem>
              <MenuItem to="/logs">Logs</MenuItem>
            </nav>
          ) : null}
        </div>
      </header>
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<IdlePage />} />
          <Route path="/session" element={<SessionPage />} />
          <Route path="/session/:sessionId" element={<SessionPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/logs" element={<LogsPage />} />
        </Routes>
      </main>
    </div>
  );
}

function MenuItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `block px-3 py-2 hover:bg-slate-800 ${isActive ? "text-emerald-400" : "text-slate-200"}`
      }
    >
      {children}
    </NavLink>
  );
}
