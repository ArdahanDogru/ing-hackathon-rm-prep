import { useT } from "../i18n";

const Block = ({ className }: { className: string }) => <div className={`animate-pulse rounded-2xl bg-gray-200/70 ${className}`} />;

/** Grey blocks in the shape of the dashboard while a run loads. */
export function DashboardSkeleton() {
  const t = useT();
  return (
    <div role="status" aria-busy="true">
      <span className="sr-only">{t("loading")}</span>
      <Block className="h-20" />
      <div className="mt-6 grid grid-cols-3 gap-3">
        <Block className="h-28" />
        <Block className="h-28" />
        <Block className="h-28" />
      </div>
      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_330px]">
        <div className="grid grid-cols-4 gap-3">
          <Block className="h-64" />
          <Block className="h-64" />
          <Block className="h-64" />
          <Block className="h-64" />
        </div>
        <Block className="h-64" />
      </div>
    </div>
  );
}
