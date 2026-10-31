import { useEffect, useId, useState } from "react";

/** Renders Mermaid source in the browser. If the source is invalid it falls back to showing the code. */
export default function MermaidDiagram({ code }: { code: string }) {
  const id = "mmd-" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setFailed(false);
    (async () => {
      try {
        const { default: mermaid } = await import("mermaid");
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "neutral",
          fontFamily: '"IBM Plex Sans", system-ui, sans-serif',
        });
        await mermaid.parse(code);
        const out = await mermaid.render(id, code);
        if (!cancelled) setSvg(out.svg);
      } catch {
        document.getElementById("d" + id)?.remove();
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, id]);

  if (failed) {
    return (
      <pre>
        <code>{code}</code>
      </pre>
    );
  }
  if (!svg) return <figure className="mermaid-figure text-sm text-muted">Drawing diagram</figure>;
  return <figure className="mermaid-figure" dangerouslySetInnerHTML={{ __html: svg }} />;
}
