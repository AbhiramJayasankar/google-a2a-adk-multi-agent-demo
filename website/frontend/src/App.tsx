import { useEffect, useState } from "react";
import { useChat } from "./store";
import { Sidebar } from "./components/Sidebar";
import { ChatLog } from "./components/ChatLog";
import { Composer } from "./components/Composer";
import { Inspector } from "./components/Inspector";
import { StatusBar } from "./components/StatusBar";

export default function App() {
  const { loadAgents, error } = useChat();
  const [inspectorOpen, setInspectorOpen] = useState(false);

  useEffect(() => {
    void loadAgents();
  }, [loadAgents]);

  return (
    <div className="h-full flex flex-col">
      <StatusBar
        onToggleInspector={() => setInspectorOpen((v) => !v)}
        inspectorOpen={inspectorOpen}
      />
      {error && (
        <div
          role="alert"
          className="px-6 py-1.5 text-[11px] font-mono text-[var(--color-err)] border-b border-[var(--color-grid)] bg-[var(--color-panel-2)] flex items-center gap-2"
        >
          <span className="text-[var(--color-err)] font-semibold tracking-wider">ERR</span>
          <span className="text-[var(--color-ink-2)]">{error}</span>
        </div>
      )}
      <div className="flex-1 flex min-h-0">
        <Sidebar />
        <main className="flex-1 flex flex-col min-w-0 border-l border-[var(--color-grid)]">
          <ChatLog />
          <Composer />
        </main>
        <Inspector open={inspectorOpen} onClose={() => setInspectorOpen(false)} />
      </div>
    </div>
  );
}
