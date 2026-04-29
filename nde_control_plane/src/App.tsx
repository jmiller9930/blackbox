import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./layout/AppShell";
import Dashboard from "./pages/Dashboard";
import Datasets from "./pages/Datasets";
import Exams from "./pages/Exams";
import Runs from "./pages/Runs";
import Settings from "./pages/Settings";
import Sources from "./pages/Sources";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="sources" element={<Sources />} />
        <Route path="datasets" element={<Datasets />} />
        <Route path="runs" element={<Runs />} />
        <Route path="exams" element={<Exams />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
