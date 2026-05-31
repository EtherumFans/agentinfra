import { useState, useRef, useCallback, useEffect } from 'react';
import { reviewsApi } from '../services/api';
import { BACKEND_BASE_URL } from '../config';

type PipelineStatus = 'idle' | 'connecting' | 'running' | 'completed' | 'failed';

interface PipelineState {
  status: PipelineStatus;
  progress: number;
  currentStep: string;
  reviewId: string | null;
  taskId: string | null;
  error: string | null;
  connectionMode: 'websocket' | 'polling' | null;
}

const PIPELINE_STEPS = [
  '提取临床证据',
  '重建临床时间线',
  '临床意义分类',
  '诊断编码',
  '手术编码',
  '病案首页生成',
  '证据闭环验证',
  'DRG/DIP 分析',
  '生成审核报告',
] as const;

function getWsUrl(backendUrl: string, taskId: string): string {
  const base = backendUrl.replace(/^http/, 'ws');
  const token = localStorage.getItem('access_token') || '';
  const sep = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${base}/api/reviews/ws/reviews/${taskId}${sep}`;
}

export function useReviewPipeline() {
  const [state, setState] = useState<PipelineState>({
    status: 'idle',
    progress: 0,
    currentStep: '',
    reviewId: null,
    taskId: null,
    error: null,
    connectionMode: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  const cleanup = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cleanup();
    };
  }, [cleanup]);

  const fetchReview = useCallback(async (reviewId: string) => {
    try {
      const r = await reviewsApi.get(reviewId);
      return r.data;
    } catch {
      return null;
    }
  }, []);

  const start = useCallback(async (encounterId: string) => {
    cleanup();
    setState({
      status: 'connecting',
      progress: 0,
      currentStep: '启动编码审核管道',
      reviewId: null,
      taskId: null,
      error: null,
      connectionMode: null,
    });

    try {
      const res = await reviewsApi.createAsync(encounterId);
      const { task_id } = res.data;
      if (!mountedRef.current) return;

      setState(prev => ({ ...prev, taskId: task_id, status: 'running', connectionMode: 'websocket' }));

      // Try WebSocket first
      const wsUrl = getWsUrl(BACKEND_BASE_URL, task_id);
      let wsConnected = false;

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        const wsTimeout = setTimeout(() => {
          if (!wsConnected && mountedRef.current) {
            ws.close();
            wsRef.current = null;
            // Fallback to polling
            setState(prev => ({ ...prev, connectionMode: 'polling' }));
            startPolling(task_id);
          }
        }, 3000);

        ws.onopen = () => {
          wsConnected = true;
          clearTimeout(wsTimeout);
          // Heartbeat: ping every 30s to detect dead connections
          const pingInterval = setInterval(() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: 'ping' }));
            } else {
              clearInterval(pingInterval);
            }
          }, 30000);
          // Clean up interval on close
          const origOnClose = ws.onclose;
          ws.onclose = (ev) => {
            clearInterval(pingInterval);
            if (origOnClose) origOnClose.call(ws, ev);
          };
        };

        ws.onmessage = (event) => {
          if (!mountedRef.current) return;
          try {
            const msg = JSON.parse(event.data);
            switch (msg.type) {
              case 'status':
                setState(prev => ({
                  ...prev,
                  status: msg.status === 'completed' ? 'completed' : msg.status === 'failed' ? 'failed' : 'running',
                  progress: msg.progress || 0,
                  currentStep: msg.current_step || '',
                }));
                break;
              case 'progress':
                setState(prev => ({
                  ...prev,
                  progress: msg.progress,
                  currentStep: msg.current_step || PIPELINE_STEPS[Math.floor(msg.progress / 12)] || '',
                }));
                break;
              case 'completed':
                setState(prev => ({
                  ...prev,
                  status: 'completed',
                  progress: 100,
                  reviewId: msg.review_id || prev.reviewId,
                }));
                break;
              case 'failed':
                setState(prev => ({
                  ...prev,
                  status: 'failed',
                  error: msg.error || 'Pipeline failed',
                }));
                break;
            }
          } catch { /* ignore parse errors */ }
        };

        ws.onerror = () => {
          if (!wsConnected) {
            ws.close();
            wsRef.current = null;
            setState(prev => ({ ...prev, connectionMode: 'polling' }));
            startPolling(task_id);
          }
        };

        ws.onclose = (event) => {
          wsRef.current = null;
          // If pipeline still running and close wasn't clean, reconnect or fall back
          if (mountedRef.current && !event.wasClean) {
            const reconnect = () => {
              if (!mountedRef.current) return;
              try {
                const rws = new WebSocket(wsUrl);
                wsRef.current = rws;
                rws.onopen = () => { /* reconnected */ };
                rws.onmessage = ws.onmessage;
                rws.onerror = ws.onerror;
                rws.onclose = ws.onclose;
              } catch {
                // Reconnect failed, fall back to polling
                if (mountedRef.current) {
                  setState(prev => ({ ...prev, connectionMode: 'polling' }));
                  startPolling(task_id);
                }
              }
            };
            setTimeout(reconnect, 1000);
          }
        };
      } catch {
        // WebSocket constructor failed, go straight to polling
        setState(prev => ({ ...prev, connectionMode: 'polling' }));
        startPolling(task_id);
      }
    } catch (err: any) {
      if (mountedRef.current) {
        setState(prev => ({
          ...prev,
          status: 'failed',
          error: err?.response?.data?.detail || err.message || 'Failed to start pipeline',
        }));
      }
    }
  }, [cleanup, fetchReview]);

  const startPolling = useCallback((taskId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);

    const poll = async () => {
      if (!mountedRef.current) {
        if (pollRef.current) clearInterval(pollRef.current);
        return;
      }
      try {
        const res = await reviewsApi.taskStatus(taskId);
        const d = res.data as any;
        const status = d.status;
        const progress = d.progress || 0;
        const current_step = d.current_step || '';
        const review_id = d.review_id || d.result_summary?.review_id || '';
        const taskError = d.error;

        if (status === 'completed') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          // Fetch full review
          const rid = review_id || '';
          const review = rid ? await fetchReview(rid) : null;
          if (mountedRef.current) {
            setState(prev => ({
              ...prev,
              status: 'completed',
              progress: 100,
              currentStep: current_step || '',
              reviewId: rid,
            }));
          }
        } else if (status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setState(prev => ({
            ...prev,
            status: 'failed',
            error: taskError || 'Pipeline failed',
          }));
        } else {
          setState(prev => ({
            ...prev,
            status: 'running',
            progress,
            currentStep: current_step || '',
          }));
        }
      } catch {
        // Polling error — keep trying
      }
    };

    poll(); // immediate first poll
    pollRef.current = setInterval(poll, 2000);
  }, [fetchReview]);

  const cancel = useCallback(() => {
    cleanup();
    setState(prev => ({ ...prev, status: 'idle', progress: 0, currentStep: '', connectionMode: null }));
  }, [cleanup]);

  const reset = useCallback(() => {
    cleanup();
    setState({
      status: 'idle',
      progress: 0,
      currentStep: '',
      reviewId: null,
      taskId: null,
      error: null,
      connectionMode: null,
    });
  }, [cleanup]);

  return { ...state, steps: PIPELINE_STEPS, start, cancel, reset };
}
