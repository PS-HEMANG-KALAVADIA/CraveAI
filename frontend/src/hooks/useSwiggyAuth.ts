import { useState, useEffect, useCallback } from 'react';

export type SwiggyConnectionStatus =
  | 'checking'
  | 'connected'
  | 'not_connected'
  | 'reauth_required'
  | 'error';

export interface SwiggyStatusResponse {
  connected: boolean;
  status: 'connected' | 'not_connected' | 'reauth_required';
  authenticated?: boolean;
  login_url?: string;
}

export function useSwiggyAuth() {
  const [status, setStatus] = useState<SwiggyConnectionStatus>('checking');
  const [loginUrl, setLoginUrl] = useState<string>('http://localhost:8000/api/swiggy/login');

  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/api/swiggy/status');
      if (res.ok) {
        const data: SwiggyStatusResponse = await res.json();
        if (data.login_url) {
          setLoginUrl(data.login_url);
        }
        if (data.status === 'connected' && data.connected) {
          setStatus('connected');
        } else if (data.status === 'reauth_required') {
          setStatus('reauth_required');
        } else {
          setStatus('not_connected');
        }
      } else {
        setStatus('error');
      }
    } catch {
      // Backend unavailable or network error
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    let isMounted = true;

    const syncStatus = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/swiggy/status');
        if (!isMounted) return;
        if (res.ok) {
          const data: SwiggyStatusResponse = await res.json();
          if (data.login_url) {
            setLoginUrl(data.login_url);
          }
          if (data.status === 'connected' && data.connected) {
            setStatus('connected');
          } else if (data.status === 'reauth_required') {
            setStatus('reauth_required');
          } else {
            setStatus('not_connected');
          }
        } else {
          setStatus('error');
        }
      } catch {
        if (isMounted) {
          setStatus('error');
        }
      }
    };

    // Initial check on startup
    syncStatus();

    // Recheck on window focus (e.g., returning from OAuth in another tab)
    const handleFocus = () => {
      syncStatus();
    };
    window.addEventListener('focus', handleFocus);
    return () => {
      isMounted = false;
      window.removeEventListener('focus', handleFocus);
    };
  }, []);

  const updateFromAuthError = useCallback((errorType: 'reauth_required' | 'not_connected') => {
    setStatus(errorType);
  }, []);

  return {
    status,
    loginUrl,
    checkStatus,
    setStatus,
    updateFromAuthError
  };
}
