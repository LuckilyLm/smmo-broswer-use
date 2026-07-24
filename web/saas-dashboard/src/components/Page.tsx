import { PageContainer } from "@ant-design/pro-components";
import { Button, Empty, Result, Skeleton } from "antd";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { findRoute } from "../app/routes";

export function Page({
  title,
  action,
  loading = false,
  children
}: {
  title: string;
  action?: ReactNode;
  loading?: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const route = findRoute(window.location.pathname);
  const breadcrumb = route ? {
    items: [
      { title: t(`nav.${route.group}`) },
      { title: t(route.nameKey) }
    ]
  } : undefined;
  return (
    <PageContainer header={{ title, breadcrumb }} extra={action ? [action] : []} loading={loading}>
      {children}
    </PageContainer>
  );
}

export function AppEmpty({ description }: { description?: ReactNode }) {
  const { t } = useTranslation();
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description || t("common.noDataDescription")} />;
}

export function PageLoading() {
  return <div className="state"><Skeleton active paragraph={{ rows: 6 }} /></div>;
}

export function PageError({ error, onRetry }: { error: string; onRetry?: () => void }) {
  const { t } = useTranslation();
  return <Result status="error" title={t("common.loadFailed")} subTitle={error} extra={onRetry ? <Button type="primary" onClick={onRetry}>{t("common.retry")}</Button> : undefined} />;
}

export function ResourceState({
  loading,
  error,
  empty,
  onRetry,
  children
}: {
  loading: boolean;
  error: string | null;
  empty: boolean;
  onRetry?: () => void;
  children: ReactNode;
}) {
  if (loading) return <PageLoading />;
  if (error) return <PageError error={error} onRetry={onRetry} />;
  if (empty) return <AppEmpty />;
  return <>{children}</>;
}
