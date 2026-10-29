import { useState, useCallback, useEffect } from 'react';
import type { LocationState } from '../types/chat';

export function useLocation() {
  const [locationState, setLocationState] = useState<LocationState>({
    status: 'unknown'
  });

  const requestLocation = useCallback(() => {
    setLocationState({ status: 'requesting' });
    
    if (!navigator.geolocation) {
      setLocationState({ status: 'unavailable' });
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocationState({
          status: 'available',
          latitude: position.coords.latitude,
          longitude: position.coords.longitude
        });
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          setLocationState({ status: 'denied' });
        } else {
          setLocationState({ status: 'unavailable' });
        }
      },
      { timeout: 10000 }
    );
  }, []);

  useEffect(() => {
    if (typeof navigator !== 'undefined' && navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: 'geolocation' as PermissionName }).then((permissionStatus) => {
        if (permissionStatus.state === 'granted') {
          requestLocation();
        } else if (permissionStatus.state === 'denied') {
          setLocationState({ status: 'denied' });
        }
        permissionStatus.onchange = () => {
          if (permissionStatus.state === 'granted') {
            requestLocation();
          } else if (permissionStatus.state === 'denied') {
            setLocationState({ status: 'denied' });
          }
        };
      }).catch(() => {
        // Fallback for browsers with restricted permissions API
      });
    }
  }, [requestLocation]);

  return { locationState, requestLocation };
}
