import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-finder">
      <ReactMarkdown remarkPlugins={[remarkGfm]}
                     components={{ a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" /> }}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

export default memo(Markdown);
