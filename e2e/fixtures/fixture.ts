import { test as base } from '@playwright/test';
import { AuthRequest } from '../requests/auth-request';

/**
 * Extends the base test with custom fixtures for API requests.
 */
export const test = base.extend<{
  authRequest: AuthRequest;
}>({
  /**
   * Provides an instance of AuthRequest.
   * @param {object} request - The request object.
   * @param {function} use - The use function to provide the fixture.
   */
  authRequest: async ({ request }, use) => {
    await use(new AuthRequest(request));
  },
});
