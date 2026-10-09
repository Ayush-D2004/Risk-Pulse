import type { ReactNode } from 'react'
import type { PipelineRun } from '../types/api'
import type { ConnectionState } from '../hooks/usePipelineStream'
import { EmptyState, ErrorState, LoadingState, SectionFrame, StatusChip } from './ui'

export interface PipelineRunViewerProps {
  activeRunId: string | null
  run: PipelineRun | null
  loading: boolean
  connectionState: ConnectionState
  streamError: Error | null
  retry: () => void
  emptyStateTitle: string
  emptyStateDetail: string
  emptyStateIcon: ReactNode
  headerRight?: ReactNode
}

export function PipelineRunViewer({
  activeRunId,
  run,
  loading,
  connectionState,
  streamError,
  retry,
  emptyStateTitle,
  emptyStateDetail,
  emptyStateIcon,
  headerRight,
}: PipelineRunViewerProps) {
  return (
    <SectionFrame eyebrow="RUNTIME" title="Pipeline Status" meta={<span className="meta-code">SSE LINK</span>}>
      {!activeRunId ? (
        <EmptyState title={emptyStateTitle} detail={emptyStateDetail} icon={emptyStateIcon} />
      ) : (
        <div className="pipeline-view">
          <div style={{ marginBottom: '16px', padding: '12px', background: '#FAFAFA', border: '1px solid #E5E7EB', borderRadius: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#6B7280' }}>RUN ID</div>
                <div style={{ fontSize: '13px', fontFamily: 'monospace' }}>{activeRunId}</div>
              </div>
              {headerRight}
            </div>
            
            <div style={{ display: 'flex', gap: '8px', marginTop: '12px', alignItems: 'center' }}>
              <StatusChip label={run?.status || 'CONNECTING'} tone={run?.status === 'FAILED' ? 'danger' : run?.status === 'COMPLETED' ? 'mint' : 'default'} />
              <span style={{ fontSize: '11px', padding: '2px 6px', background: '#E5E7EB', borderRadius: '4px' }}>{connectionState.toUpperCase()}</span>
            </div>
          </div>

          {streamError && (
              <div style={{ marginBottom: '16px' }}>
                <ErrorState title="Stream error" detail={streamError.message} onRetry={retry} />
              </div>
          )}

          {loading && !run && <LoadingState />}

          {run && (
            <div className="pipeline-stages">
              <div className="section-eyebrow" style={{ marginBottom: '8px' }}>STAGES</div>
              {run.stages.map((stage) => (
                <div key={stage.name} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #E5E7EB', fontSize: '13px' }}>
                  <span style={{ fontWeight: 'bold' }}>{stage.name}</span>
                  <StatusChip label={stage.status} tone={stage.status === 'FAILED' ? 'danger' : stage.status === 'COMPLETED' ? 'mint' : stage.status === 'SKIPPED' ? 'amber' : 'default'} />
                </div>
              ))}
              
              {run.error && (
                <div style={{ marginTop: '16px', padding: '12px', borderLeft: '3px solid #EF4444', background: '#FEF2F2', fontSize: '13px', color: '#B91C1C' }}>
                  <strong>Pipeline Error:</strong> {run.error}
                </div>
              )}

              {run.final_result && (
                <div style={{ marginTop: '16px' }}>
                  <div className="section-eyebrow" style={{ marginBottom: '8px' }}>FINAL RESULT</div>
                  <div style={{ padding: '12px', background: '#111827', color: '#F9FAFB', borderRadius: '4px', fontSize: '12px', fontFamily: 'monospace', overflowX: 'auto', whiteSpace: 'pre' }}>
                    {JSON.stringify(run.final_result, null, 2)}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </SectionFrame>
  )
}
