import { APIRequestContext, Page, expect } from '@playwright/test';

export const SIMULATOR = process.env.KUNTUR_SIM_URL ?? 'http://127.0.0.1:15000';

export function password(account: 'operador' | 'visitante'): string {
  const name = account === 'operador' ? 'KUNTUR_OPERATOR_PASSWORD' : 'KUNTUR_VIEWER_PASSWORD';
  const value = process.env[name];
  if (!value) throw new Error(`Export ${name} (the same value docker compose uses)`);
  return value;
}

export async function signIn(page: Page, account: 'operador' | 'visitante'): Promise<void> {
  await page.goto('/ingresar');
  await page.getByLabel('Usuario').fill(account);
  await page.getByLabel('Contraseña').fill(password(account));
  await page.getByRole('button', { name: 'Ingresar' }).click();
  await expect(page.getByRole('heading', { name: 'Flota' })).toBeVisible();
}

/** Talks to the simulator's control API: the test plays the field, the browser plays the operator. */
export class Field {
  constructor(private readonly request: APIRequestContext) {}

  async scenario(name: string, deviceId: string): Promise<void> {
    const response = await this.request.post(`${SIMULATOR}/sim/scenarios/${name}`, { data: { device_id: deviceId } });
    expect(response.status(), await response.text()).toBe(202);
  }

  async fault(deviceId: string, mode: 'NONE' | 'DOWN' | 'TIMEOUT'): Promise<void> {
    const response = await this.request.put(`${SIMULATOR}/sim/devices/${deviceId}/fault`, { data: { mode } });
    expect(response.ok()).toBeTruthy();
  }

  async conditions(deviceId: string, changes: Record<string, unknown>): Promise<void> {
    const response = await this.request.patch(`${SIMULATOR}/sim/devices/${deviceId}/conditions`, { data: changes });
    expect(response.ok(), await response.text()).toBeTruthy();
  }
}
