import { describe, it } from 'node:test';
import assert from 'node:assert';

// Mock state machine replicating useSwiggyAuth logic
class SwiggyAuthStateMachine {
  constructor(fetchImpl = null) {
    this.status = 'checking'; // Requirement 9: Frontend startup never displaying connected before receiving backend result
    this.loginUrl = 'http://localhost:8000/api/swiggy/login';
    this.fetchImpl = fetchImpl;
  }

  async checkStatus() {
    try {
      if (!this.fetchImpl) {
        throw new Error('Network error: backend offline');
      }
      const res = await this.fetchImpl('http://localhost:8000/api/swiggy/status');
      if (res && res.ok) {
        const data = await res.json();
        if (data.login_url) {
          this.loginUrl = data.login_url;
        }
        if (data.status === 'connected' && data.connected) {
          this.status = 'connected';
        } else if (data.status === 'reauth_required') {
          this.status = 'reauth_required';
        } else {
          this.status = 'not_connected';
        }
      } else {
        this.status = 'error';
      }
    } catch {
      // Backend unavailable or network error
      this.status = 'error';
    }
  }

  updateFromAuthError(errorType) {
    this.status = errorType;
  }

  // Handle restaurant search result like useChat onResult / onError
  handleSearchResult(resultData) {
    if (resultData.auth_status === 'reauth_required') {
      this.updateFromAuthError('reauth_required');
    } else if (resultData.auth_status === 'not_connected') {
      this.updateFromAuthError('not_connected');
    } else if (resultData.response) {
      const respLower = resultData.response.toLowerCase();
      if (respLower.includes('session expired') || respLower.includes('re-authenticate')) {
        this.updateFromAuthError('reauth_required');
      } else if (respLower.includes('swiggy authentication missing') || (respLower.includes('connect to swiggy') && respLower.includes('swiggy/login'))) {
        this.updateFromAuthError('not_connected');
      }
    }
    // Unrelated errors (empty results, network timeout) do not alter connection status
  }
}

describe('Swiggy Connection Status and Lifecycle Tests', () => {
  it('Requirement 9: Initial startup state is checking and never connected before backend response', () => {
    const auth = new SwiggyAuthStateMachine();
    assert.strictEqual(auth.status, 'checking');
    assert.notStrictEqual(auth.status, 'connected');
  });

  it('Requirement 5: Backend unavailable during status check displays error, never falsely connected', async () => {
    // Simulated connection refused
    const offlineFetch = async () => {
      throw new Error('Failed to fetch: Connection refused');
    };
    const auth = new SwiggyAuthStateMachine(offlineFetch);
    assert.strictEqual(auth.status, 'checking');
    await auth.checkStatus();
    assert.strictEqual(auth.status, 'error');
    assert.notStrictEqual(auth.status, 'connected');
  });

  it('Requirement 1 & 2: Missing or invalid token reports not_connected', async () => {
    const mockFetch = async () => ({
      ok: true,
      json: async () => ({
        connected: false,
        status: 'not_connected',
        authenticated: false,
        login_url: 'http://localhost:8000/api/swiggy/login'
      })
    });
    const auth = new SwiggyAuthStateMachine(mockFetch);
    await auth.checkStatus();
    assert.strictEqual(auth.status, 'not_connected');
  });

  it('Requirement 3 & 4: Valid stored credentials report connected', async () => {
    const mockFetch = async () => ({
      ok: true,
      json: async () => ({
        connected: true,
        status: 'connected',
        authenticated: true,
        login_url: 'http://localhost:8000/api/swiggy/login'
      })
    });
    const auth = new SwiggyAuthStateMachine(mockFetch);
    await auth.checkStatus();
    assert.strictEqual(auth.status, 'connected');
  });

  it('Requirement 4: Known invalid refresh token reports reauth_required', async () => {
    const mockFetch = async () => ({
      ok: true,
      json: async () => ({
        connected: false,
        status: 'reauth_required',
        authenticated: false,
        login_url: 'http://localhost:8000/api/swiggy/login'
      })
    });
    const auth = new SwiggyAuthStateMachine(mockFetch);
    await auth.checkStatus();
    assert.strictEqual(auth.status, 'reauth_required');
  });

  it('Requirement 6: Status refresh after OAuth login callback transitions to connected', async () => {
    let isAuthenticated = false;
    const dynamicFetch = async () => ({
      ok: true,
      json: async () => ({
        connected: isAuthenticated,
        status: isAuthenticated ? 'connected' : 'not_connected',
        authenticated: isAuthenticated,
        login_url: 'http://localhost:8000/api/swiggy/login'
      })
    });

    const auth = new SwiggyAuthStateMachine(dynamicFetch);
    await auth.checkStatus();
    assert.strictEqual(auth.status, 'not_connected');

    // User completes OAuth callback
    isAuthenticated = true;
    await auth.checkStatus();
    assert.strictEqual(auth.status, 'connected');
  });

  it('Requirement 7: Status update after an authentication-related restaurant-search failure', async () => {
    const auth = new SwiggyAuthStateMachine();
    auth.status = 'connected'; // Initially connected

    // Restaurant search failed due to expired session
    auth.handleSearchResult({
      auth_status: 'reauth_required',
      response: 'Swiggy session expired. Please re-authenticate at /api/swiggy/login',
      tools_used: ['search_nearby_restaurants_failed'],
      restaurants: []
    });

    assert.strictEqual(auth.status, 'reauth_required');
  });

  it('Requirement 8: Unrelated restaurant-search errors do NOT incorrectly change connection status', async () => {
    const auth = new SwiggyAuthStateMachine();
    auth.status = 'connected'; // Initially connected

    // Normal empty result
    auth.handleSearchResult({
      response: 'I could not find any restaurants serving this dish nearby.',
      tools_used: ['search_nearby_restaurants_no_results'],
      restaurants: []
    });
    assert.strictEqual(auth.status, 'connected');

    // Generic network timeout or temporary outage
    auth.handleSearchResult({
      response: 'Temporary service error occurred. Please try again.',
      tools_used: ['search_nearby_restaurants_failed'],
      restaurants: []
    });
    assert.strictEqual(auth.status, 'connected');
  });
});
