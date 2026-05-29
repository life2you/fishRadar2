import type { ResultInsights, ResultItem } from '@/types/result.d.ts'
import { http } from '@/lib/http'

export interface GetResultContentParams {
  recommended_only?: boolean;
  ai_recommended_only?: boolean;
  keyword_recommended_only?: boolean;
  include_hidden?: boolean;
  sort_by?: 'crawl_time' | 'publish_time' | 'price' | 'keyword_hit_count';
  sort_order?: 'asc' | 'desc';
  page?: number;
  limit?: number;
  tenant_id?: number;
}

export async function getResultFiles(tenantId?: number | null): Promise<string[]> {
  const data = await http('/api/results/files', {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  })
  return data.files || []
}

export async function deleteResultFile(filename: string, tenantId?: number | null): Promise<{ message: string }> {
  return await http(`/api/results/files/${filename}`, {
    method: 'DELETE',
    params: tenantId ? { tenant_id: tenantId } : undefined,
  })
}

export async function getResultContent(
  filename: string,
  params: GetResultContentParams = {}
): Promise<{ total_items: number; items: ResultItem[] }> {
  return await http(`/api/results/${filename}`, { params: params as Record<string, any> })
}

export async function getResultInsights(filename: string, tenantId?: number): Promise<ResultInsights> {
  return await http(`/api/results/${filename}/insights`, {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  })
}

export async function getResultBlacklistRules(filename: string, tenantId?: number): Promise<{ keywords: string[] }> {
  return await http(`/api/results/${filename}/blacklist-rules`, {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  })
}

export async function updateResultBlacklistRules(
  filename: string,
  keywords: string[],
  tenantId?: number,
): Promise<{ message: string; keywords: string[] }> {
  return await http(`/api/results/${filename}/blacklist-rules`, {
    method: 'PUT',
    params: tenantId ? { tenant_id: tenantId } : undefined,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keywords }),
  })
}

export function buildResultExportUrl(filename: string, params: GetResultContentParams = {}): string {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      searchParams.set(key, String(value))
    }
  })
  const queryString = searchParams.toString()
  return `/api/results/${encodeURIComponent(filename)}/export${queryString ? `?${queryString}` : ''}`
}

export function downloadResultExport(filename: string, params: GetResultContentParams = {}) {
  const url = buildResultExportUrl(filename, params)
  const link = document.createElement('a')
  link.href = url
  link.download = ''
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

export async function updateItemStatus(
  filename: string,
  itemId: string,
  status: string,
  tenantId?: number,
): Promise<{ message: string; status: string }> {
  return await http(`/api/results/${filename}/items/${itemId}/status`, {
    method: 'PATCH',
    params: tenantId ? { tenant_id: tenantId } : undefined,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

export async function reanalyzeResultFile(
  filename: string,
  tenantId?: number | null,
): Promise<{
  message: string
  task_id: number | null
  task_name: string
  updated_count: number
  failed_count: number
  total_count: number
}> {
  return await http(`/api/results/${filename}/reanalyze`, {
    method: 'POST',
    params: tenantId ? { tenant_id: tenantId } : undefined,
  })
}
