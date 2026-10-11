// A small Markdown renderer for the edited meeting text: headings, paragraphs,
// "-" / "*" lists and **bold**. It builds React elements, so HTML in the text
// stays text (no innerHTML).
import type { ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  );
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let para: string[] = [];
  let list: string[] = [];
  const flush = () => {
    if (para.length) blocks.push(<p key={blocks.length} className="my-3">{inline(para.join(" "))}</p>);
    if (list.length)
      blocks.push(
        <ul key={blocks.length} className="my-3 list-disc pl-6">
          {list.map((li, i) => (
            <li key={i}>{inline(li)}</li>
          ))}
        </ul>,
      );
    para = [];
    list = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    const li = /^\s*[-*]\s+(.*)$/.exec(line);
    if (h) {
      flush();
      const level = h[1].length;
      const cls = ["", "text-2xl", "text-xl", "text-lg", "text-base"][level];
      const Tag = `h${level}` as "h1" | "h2" | "h3" | "h4";
      blocks.push(
        <Tag key={blocks.length} className={`${cls} mb-2 mt-5 font-bold`}>
          {inline(h[2])}
        </Tag>,
      );
    } else if (li) {
      if (para.length) flush();
      list.push(li[1]);
    } else if (!line.trim()) {
      flush();
    } else {
      if (list.length) flush();
      para.push(line.trim());
    }
  }
  flush();
  return <div>{blocks}</div>;
}
