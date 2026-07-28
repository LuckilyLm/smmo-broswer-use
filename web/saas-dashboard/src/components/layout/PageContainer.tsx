import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

type PageWidth = "dashboard" | "content" | "form" | "full";

const widthClasses: Record<PageWidth, string> = {
  dashboard: "max-w-[1600px]",
  content: "max-w-[1200px]",
  form: "max-w-[960px]",
  full: "max-w-none",
};

interface PageContainerProps extends ComponentProps<"div"> {
  children: ReactNode;
  maxWidth?: PageWidth;
}

export default function PageContainer({
  children,
  maxWidth = "dashboard",
  className,
  ...props
}: PageContainerProps) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-4 py-4 sm:px-5 md:px-6 md:py-6 2xl:px-8",
        widthClasses[maxWidth],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
