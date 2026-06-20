/**
 * WebSocket live-push hook (08 §5).
 *
 * Subscribes to wss://<host>/api/v1/stream?token=<read-token>. Pushes frames
 * (signal/snapshot/decision/risk/status/trade/alert/heartbeat). On drop it falls
 * back to REST polling (handled by TanStack Query refetchInterval); on reconnect
 * the caller should re-fetch /status + /risk to resync.
 *
 * In mock mode the socket is simulated: it emits periodic frames from the mock
 * layer so the Live screen updates without a backend.
 */

import { useEffect, useRef, useState } from 'react';
import { config } from './config';
import { getToken } from './secure';
import * as mock from './mock';
import type { Alert, Decision, MarketSnapshot, RiskState, Signal, BotStatus } from '@/types';

export type WsFrame =
  | { type: 'signal'; ts: string; data: Signal }
  | { type: 'snapshot'; ts: string; data: MarketSnapshot }
  | { type: 'decision'; ts: string; data: Decision }
  | { type: 'risk'; ts: string; data: RiskState }
  | { type: 'status'; ts: string; data: BotStatus }
  | { type: 'alert'; ts: string; data: Alert }
  | { type: 'heartbeat'; ts: string; data: { age_sec: number } };

export type WsStatus = 'connecting' | 'open' | 'closed';

interface UseStreamResult {
  status: WsStatus;
  lastFrame: WsFrame | null;
  lastAlert: Alert | null;
}

/**
 * Subscribe to the live stream. `onFrame` is invoked per frame (e.g. to seed the
 * query cache). Returns connection status and the most recent frame/alert.
 */
export function useStream(onFrame?: (frame: WsFrame) => void): UseStreamResult {
  const [status, setStatus] = useState<WsStatus>('connecting');
  const [lastFrame, setLastFrame] = useState<WsFrame | null>(null);
  const [lastAlert, setLastAlert] = useState<Alert | null>(null);
  const onFrameRef = useRef(onFrame);
  onFrameRef.current = onFrame;

  useEffect(() => {
    let cancelled = false;
    const timers: ReturnType<typeof setInterval>[] = [];
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let backoff = 1000;

    const emit = (frame: WsFrame) => {
      if (cancelled) return;
      setLastFrame(frame);
      if (frame.type === 'alert') setLastAlert(frame.data);
      onFrameRef.current?.(frame);
    };

    // ---- Mock mode: simulate the socket with timers ----
    if (config.useMock) {
      setStatus('open');
      timers.push(
        setInterval(() => emit({ type: 'signal', ts: new Date().toISOString(), data: mock.mockSignal() }), 1000),
      );
      timers.push(
        setInterval(() => emit({ type: 'snapshot', ts: new Date().toISOString(), data: mock.mockSnapshot() }), 2000),
      );
      timers.push(
        setInterval(() => emit({ type: 'risk', ts: new Date().toISOString(), data: mock.mockRisk() }), 5000),
      );
      timers.push(
        setInterval(
          () => emit({ type: 'heartbeat', ts: new Date().toISOString(), data: { age_sec: 2 } }),
          8000,
        ),
      );
      return () => {
        cancelled = true;
        timers.forEach(clearInterval);
      };
    }

    // ---- Live mode ----
    const connect = async () => {
      if (cancelled) return;
      setStatus('connecting');
      const token = await getToken('read');
      const url = `${config.wsBaseUrl}/stream${token ? `?token=${encodeURIComponent(token)}` : ''}`;
      socket = new WebSocket(url);

      socket.onopen = () => {
        if (cancelled) return;
        backoff = 1000;
        setStatus('open');
      };
      socket.onmessage = (ev: WebSocketMessageEvent) => {
        try {
          const frame = JSON.parse(String(ev.data)) as WsFrame;
          emit(frame);
        } catch {
          // ignore malformed frames
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
      socket.onclose = () => {
        if (cancelled) return;
        setStatus('closed');
        // Reconnect with backoff (08 §5).
        backoff = Math.min(backoff * 2, 15000);
        reconnectTimer = setTimeout(connect, backoff);
      };
    };

    void connect();

    return () => {
      cancelled = true;
      timers.forEach(clearInterval);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  return { status, lastFrame, lastAlert };
}
