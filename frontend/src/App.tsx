import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import WritePage from "./pages/WritePage";
import LibraryPage from "./pages/LibraryPage";
import EditorPage from "./pages/EditorPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<WritePage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="blogs/:id" element={<EditorPage />} />
        <Route path="*" element={<p className="text-muted">Page not found.</p>} />
      </Route>
    </Routes>
  );
}
