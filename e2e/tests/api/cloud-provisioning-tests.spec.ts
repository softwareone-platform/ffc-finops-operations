import { test } from '../../fixtures/fixture';
import { generateRandomEmail, generateRandomOrganizationName } from '../../utils/random-data-generator';
import { getAccessToken } from '../../utils/getAccessToken';
import { expect } from 'playwright/test';
import { debugLog } from '../../utils/debug-logging';
import { v4 as uuidv4 } from 'uuid';
import { getNewEmployeeID } from '../../utils/getNewEmployeeID';
import { GetEmployeesByOrganisationIDResponse } from '../../types/get-employees-by-organization-id';
import { deleteOrganization } from '../../utils/delete-organization';
import { GetOrganizationByIDResponse } from '../../types/get-organizations-by-id-response';

let createEmployeeData: {
  display_name: string;
  email: string;
};

let createOrgData: {
  name: string;
  currency: string;
  billing_currency: string;
  operations_external_id: string;
  user_id: string;
};

async function setNewEmployeeData() {
  createEmployeeData = {
    display_name: `Test Employee ${Date.now()}`,
    email: generateRandomEmail(),
  };
}

async function setNewOrganizationData() {
  createOrgData = {
    name: generateRandomOrganizationName(),
    currency: 'EUR',
    billing_currency: 'EUR',
    operations_external_id: uuidv4(),
    user_id: await getNewEmployeeID(),
  };
}

test.describe('Cloud Provisioning tests', { tag: '@cloud-provisioning' }, () => {
  let headers: { [key: string]: string };
  let organizationID: string;

  test.beforeAll(async () => {
    headers = {
      Authorization: `Bearer ${await getAccessToken()}`,
      'Content-Type': 'application/json',
    };
  });

  test.afterEach(async () => {
    createEmployeeData = null;
    if (organizationID) {
      await deleteOrganization(headers, organizationID);
      organizationID = '';
      createOrgData = null;
    }
  });

  test('Create a new employee', { tag: '@p1' }, async ({ cloudProvisioningRequest }) => {
    await setNewEmployeeData();
    const response = await cloudProvisioningRequest.createEmployee(headers, createEmployeeData);
    const { email, display_name, roles_count, id } = await response.json();

    debugLog(`Created Employee ID: ${id}`);

    expect(response.status()).toBe(201);
    expect(display_name).toBe(createEmployeeData.display_name);
    expect(id).toBeTruthy();
    expect(email).toBe(createEmployeeData.email);
    expect(roles_count).toBeFalsy();
  });

  test('Create Organization', { tag: '@p1' }, async ({ cloudProvisioningRequest }) => {
    await setNewOrganizationData();
    const response = await cloudProvisioningRequest.createOrganization(headers, createOrgData);
    const { id } = await response.json();
    debugLog(`Created Organization ID: ${id}`);
    organizationID = id;

    expect(response.status()).toBe(201);
    expect(id).toMatch(/^FORG-\d{4}-\d{4}-\d{4}$/);
  });

  test('Update Organization', { tag: '@p1' }, async ({ cloudProvisioningRequest }) => {
    await setNewOrganizationData();
    organizationID = await cloudProvisioningRequest.getNewOrganizationID(headers, createOrgData);
    const updateData = {
      name: generateRandomOrganizationName(),
      operations_external_id: uuidv4(),
    };
    const response = await cloudProvisioningRequest.updateOrganization(headers, organizationID, updateData);
    const { name, operations_external_id } = await response.json();

    expect(response.status()).toBe(200);
    expect(name).toBe(updateData.name);
    expect(operations_external_id).toBe(updateData.operations_external_id);
  });

  test('Delete Organization by ID', { tag: '@p1' }, async ({ cloudProvisioningRequest }) => {
    await setNewOrganizationData();
    organizationID = await cloudProvisioningRequest.getNewOrganizationID(headers, createOrgData);
    const response = await cloudProvisioningRequest.deleteOrganization(headers, organizationID);

    expect(response.status()).toBe(204);
    organizationID = '';
  });

  test('Get Employees by Organization ID', { tag: '@p1' }, async ({ cloudProvisioningRequest }) => {
    await setNewEmployeeData();
    const employeeId = await cloudProvisioningRequest.getCreateEmployeeID(headers, createEmployeeData);
    debugLog(`Created Employee ID: ${employeeId}`);

    const orgData = {
      name: generateRandomOrganizationName(),
      currency: 'EUR',
      billing_currency: 'EUR',
      operations_external_id: uuidv4(),
      user_id: employeeId,
    };

    organizationID = await cloudProvisioningRequest.getNewOrganizationID(headers, orgData);
    const orgResponse = await cloudProvisioningRequest.getEmployeesByOrganizationId(headers, organizationID);
    const payload = JSON.parse(await orgResponse.text()) as GetEmployeesByOrganisationIDResponse;

    expect(orgResponse.status()).toBe(200);
    expect.soft(payload.length).toBe(1);
    expect.soft(payload[0].email).toBe(createEmployeeData.email);
    expect.soft(payload[0].display_name).toBe(createEmployeeData.display_name);
  });

  test('Get Employee by email', { tag: '@p1' }, async ({ cloudProvisioningRequest }) => {
    await setNewEmployeeData();
    await cloudProvisioningRequest.createEmployee(headers, createEmployeeData);

    const response = await cloudProvisioningRequest.getEmployeeByEmail(headers, createEmployeeData.email);
    const payload = await response.json();

    expect(response.status()).toBe(200);
    expect(payload.email).toBe(createEmployeeData.email);
    expect(payload.display_name).toBe(createEmployeeData.display_name);
  });

  test('Get all organizations', async ({ cloudProvisioningRequest }) => {
    const response = await cloudProvisioningRequest.getOrganizations(headers, 200);
    const organizations = await response.json();

    debugLog(`Organizations Response: ${JSON.stringify(organizations)}`);

    expect(response.status()).toBe(200);
  });

  test('Get organization by ID', async ({ cloudProvisioningRequest }) => {
    const id = process.env.OPS_ORG_ID;
    const response = await cloudProvisioningRequest.getOrganizationById(headers, id);
    const payload = (await response.json()) as GetOrganizationByIDResponse;

    expect(response.status()).toBe(200);
    expect(payload.id).toBe(id);
    expect(payload.name).toBe('SoftwareOne (Test Environment)');
  });
});
