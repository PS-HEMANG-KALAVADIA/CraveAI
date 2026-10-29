import React from 'react';
import type { LocationState } from '../../types/chat';

interface Props {
  locationState: LocationState;
  onRequest: () => void;
}

export const LocationPermission: React.FC<Props> = ({ locationState, onRequest }) => {
  if (locationState.status === 'available') {
    return (
      <div className="location-status success" title="Location access granted">
        <span className="status-dot success" aria-hidden="true"></span>
        Location enabled
      </div>
    );
  }
  
  if (locationState.status === 'requesting') {
    return (
      <div className="location-status pending">
        <span className="status-dot checking" aria-hidden="true"></span>
        Detecting location…
      </div>
    );
  }
  
  if (locationState.status === 'denied') {
    return (
      <div className="location-status error" title="Location access denied. Ask with city name.">
        <span className="status-dot error" aria-hidden="true"></span>
        Location off
      </div>
    );
  }
  
  if (locationState.status === 'unavailable') {
    return (
      <div className="location-status error" title="Location unavailable">
        <span className="status-dot error" aria-hidden="true"></span>
        Location unavailable
      </div>
    );
  }

  // Unknown state - allow request
  return (
    <div className="location-status request">
      <button type="button" onClick={onRequest} className="location-btn">
        📍 Enable location
      </button>
    </div>
  );
};
