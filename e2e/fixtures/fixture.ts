import { test as base } from '@playwright/test';
import { AuthRequest } from '../requests/auth-request';
import { CloudProvisioningRequest } from '../requests/cloudProvisioningRequest';

/**
 * Extends the base test with custom fixtures for API requests.
 */
export const test = base.extend<{
  authRequest: AuthRequest;
  cloudProvisioningRequest: CloudProvisioningRequest;
}>({
  authRequest: async ({ request }, use) => {
    await use(new AuthRequest(request));
  },
  cloudProvisioningRequest: async ({ request }, use) => {
    await use(new CloudProvisioningRequest(request));
  },
});
