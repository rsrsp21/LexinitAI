import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="space-y-5 text-[15px] leading-7 text-foreground/90 sm:text-base [&_.katex-display]:overflow-x-auto [&_.katex-display]:overflow-y-hidden [&_.katex-display]:py-2 [&_.katex]:text-foreground">
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          h1: ({ children }) => (
            <h2 className="font-display text-2xl font-semibold tracking-tight text-foreground">
              {children}
            </h2>
          ),
          h2: ({ children }) => (
            <h2 className="font-display text-2xl font-semibold tracking-tight text-foreground">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="font-display text-xl font-semibold tracking-tight text-foreground">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-base font-semibold text-foreground">
              {children}
            </h4>
          ),
          p: ({ children }) => <p>{children}</p>,
          ul: ({ children }) => (
            <ul className="space-y-2 pl-5 list-disc">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="space-y-2 pl-5 list-decimal">{children}</ol>
          ),
          li: ({ children }) => <li>{children}</li>,
          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">
              {children}
            </strong>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-accent underline-offset-4 hover:underline"
            >
              {children}
            </a>
          ),
          code: ({ children, className }) => {
            const isBlock = Boolean(className);
            if (isBlock) {
              return <code className={className}>{children}</code>;
            }
            return (
              <code className="rounded-md bg-muted px-1.5 py-0.5 text-sm text-foreground">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="app-scrollbar overflow-x-auto rounded-xl border border-border bg-muted p-4 text-sm leading-6 text-foreground">
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-accent pl-4 text-muted-foreground">
              {children}
            </blockquote>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
