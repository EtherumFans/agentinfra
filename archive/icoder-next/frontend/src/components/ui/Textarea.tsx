import type { TextareaHTMLAttributes } from "react";
import { cn } from "../../design/cn";

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded-lg border border-line bg-panel p-3 font-mono text-[13px] leading-7 text-ink",
        "placeholder:text-faint focus-visible:border-teal resize-y",
        className,
      )}
      {...rest}
    />
  );
}
