import { test } from '../../fixtures/fixture';
import { debugLog } from '../../utils/debug-logging';
import { expect } from 'playwright/test';

test.describe('Authentication API Tests', () => {
  test.describe.configure({ mode: 'default' });
  const email = process.env.DEFAULT_USER_EMAIL;
  const password = process.env.DEFAULT_USER_PASSWORD;
  const accountId = process.env.DEFAULT_ACCOUNT_ID;
  let accessToken: string;
  let refreshToken: string;

  test('Get token for Operations API', async ({ authRequest }) => {
    accessToken = await authRequest.getTokenForSpecificAccount(email, password, accountId);
    debugLog(`Access Token: ${accessToken}`);
    expect(accessToken).toBeTruthy();
  });

  test('Get token for last used account', async ({ authRequest }) => {
    accessToken = await authRequest.getTokenForLastUsedAccount(email, password);
    debugLog(`Access Token: ${accessToken}`);
    expect(accessToken).toBeTruthy();
  });

  test('Refresh token for Operations API', async ({ authRequest }) => {
    refreshToken = await authRequest.getRefreshToken(email, password, accountId);
    const newAccessToken = await authRequest.getAccessTokenWithRefreshToken(refreshToken, accountId);
    debugLog(`New Access Token: ${newAccessToken}`);
    expect(newAccessToken).toBeTruthy();
  });
});
