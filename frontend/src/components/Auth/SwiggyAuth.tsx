import React from 'react';
import { useSwiggyAuth, type SwiggyConnectionStatus } from '../../hooks/useSwiggyAuth';

export interface SwiggyAuthProps {
  status?: SwiggyConnectionStatus;
  loginUrl?: string;
  onRefresh?: () => void;
}

export const SwiggyAuth: React.FC<SwiggyAuthProps> = (props) => {
  // If props are not provided, fall back to internal hook
  const internalAuth = useSwiggyAuth();
  const status = props.status !== undefined ? props.status : internalAuth.status;
  const loginUrl = props.loginUrl || internalAuth.loginUrl || 'http://localhost:8000/api/swiggy/login';
  const onRefresh = props.onRefresh || internalAuth.checkStatus;

  if (status === 'checking') {
    return (
      <span
        id="swiggy-status-checking"
        className="swiggy-auth-badge checking"
        title="Checking connection to Swiggy..."
      >
        <span className="status-dot checking" aria-hidden="true"></span>
        Checking connection…
      </span>
    );
  }

  if (status === 'connected') {
    return (
      <span
        id="swiggy-status-connected"
        className="swiggy-auth-badge connected"
        title="Authenticated with Swiggy MCP"
      >
        <span className="status-dot success" aria-hidden="true"></span>
        Swiggy Connected
      </span>
    );
  }

  if (status === 'reauth_required') {
    return (
      <a
        id="swiggy-status-reauth"
        href={loginUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="swiggy-auth-btn reauth-required"
        title="Swiggy session expired. Click to re-authenticate"
      >
        <span className="status-dot warning" aria-hidden="true"></span>
        Reconnect Required
      </a>
    );
  }

  if (status === 'error') {
    return (
      <span
        id="swiggy-status-error"
        className="swiggy-auth-badge error"
        title="Unable to verify connection status. Click to retry."
        onClick={onRefresh}
        style={{ cursor: 'pointer' }}
      >
        <span className="status-dot error" aria-hidden="true"></span>
        Unable to Check Connection
      </span>
    );
  }

  // status === 'not_connected'
  return (
    <a
      id="swiggy-status-not-connected"
      href={loginUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="swiggy-auth-btn not-connected"
      title="Click to authenticate with your Swiggy account"
    >
      <span className="status-dot not-connected" aria-hidden="true"></span>
      Swiggy Not Connected
    </a>
  );
};
