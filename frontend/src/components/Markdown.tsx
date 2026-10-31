import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MermaidDiagram from "./MermaidDiagram";

/** Renders post markdown. Relative `images/x.jpg` links are served from /media/<id>/. */
export default function Markdown({ source, blogId }: { source: string; blogId: number }) {
  return (
    <div className="article">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: ({ src, alt }) => (
            <img
              alt={alt ?? ""}
              src={src?.startsWith("images/") ? `/media/${blogId}/${src.slice("images/".length)}` : src}
            />
          ),
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          pre: ({ node, children }) => {
            const child = node?.children?.[0] as any;
            const classes: string[] = child?.properties?.className ?? [];
            if (child?.tagName === "code" && classes.includes("language-mermaid")) {
              const code = (child.children ?? []).map((c: any) => c.value ?? "").join("").trim();
              return <MermaidDiagram code={code} />;
            }
            return <pre>{children}</pre>;
          },
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
