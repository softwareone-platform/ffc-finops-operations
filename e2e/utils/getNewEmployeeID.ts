import { getAccessToken } from './getAccessToken';
import { request } from '@playwright/test';
import { CloudProvisioningRequest } from '../requests/cloudProvisioningRequest';
import { generateRandomEmail } from './random-data-generator';

export async function getNewEmployeeID(): Promise<string> {
  const context = await request.newContext();
  const cloudProvisioningRequest = new CloudProvisioningRequest(context);

  const headers = {
    Authorization: `Bearer ${await getAccessToken()}`,
    'Content-Type': 'application/json',
  };

  const data = {
    display_name: `Test Employee ${Date.now()}`,
    email: generateRandomEmail(),
  };

  return await cloudProvisioningRequest.getCreateEmployeeID(headers, data);
}
