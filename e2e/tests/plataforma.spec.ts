import { ConsoleMessage, expect, test } from '@playwright/test';

import { Field, signIn } from './support';

test.describe('Kuntur SCADA de punta a punta', () => {
  test('un visitante ve la flota en vivo y no puede enviar órdenes @tableta', async ({ page }) => {
    const policyViolations: string[] = [];
    page.on('console', (message: ConsoleMessage) => {
      if (message.type() === 'error' && /Content Security Policy/i.test(message.text())) {
        policyViolations.push(message.text());
      }
    });

    await signIn(page, 'visitante');
    await expect(page.locator('kt-device-tile')).toHaveCount(7);
    await expect(page.getByText('En vivo')).toBeVisible();

    await page.getByRole('link', { name: /UPS sala eléctrica Norte/ }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'UPS sala eléctrica Norte' })).toBeVisible();
    await expect(page.getByText('Tu cuenta solo puede mirar')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Probar la batería' })).toHaveCount(0);
    expect(policyViolations).toEqual([]);
  });

  test('una falla en el campo llega en vivo como alarma, con su explicación', async ({ page, request }) => {
    const field = new Field(request);
    await signIn(page, 'operador');
    await field.fault('barrera-sur-01', 'DOWN');
    try {
      const banner = page.getByRole('banner');
      await expect(banner.getByText(/\d+ críticas?/)).toBeVisible({ timeout: 60_000 });
      await expect(banner.getByRole('link', { name: /Sin comunicación en Barrera acceso Sur/ })).toBeVisible();
      await expect(
        page.locator('kt-device-tile', { hasText: 'Barrera acceso Sur' }).getByText('Sin comunicación'),
      ).toBeVisible();

      await page.getByRole('link', { name: 'Alertas' }).click();
      await page.getByRole('button', { name: /Sin comunicación\s+Barrera acceso Sur/ }).click();
      await expect(page.getByRole('heading', { name: 'Qué revisar, en este orden' })).toBeVisible();
      await expect(page.getByText(/plantilla de Kuntur|escrita por Claude/)).toBeVisible();
    } finally {
      await field.fault('barrera-sur-01', 'NONE');
    }
  });

  test('una orden se confirma, se cumple y queda auditada con su autor', async ({ page }) => {
    await signIn(page, 'operador');
    await page.goto('/equipos/barrera-norte-01');
    await page.getByRole('button', { name: 'Cerrar la barrera' }).click();
    await page.getByRole('button', { name: 'Enviar la orden' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Orden cumplida' })).toBeVisible();

    await page.getByRole('link', { name: 'Auditoría' }).click();
    const row = page.getByRole('row', { name: /Barrera acceso Norte.*Cerrar la barrera.*operador.*Cumplida/ });
    await expect(row.first()).toBeVisible();
  });

  test('el ingreso rechaza una contraseña equivocada sin decir qué falló', async ({ page }) => {
    await page.goto('/ingresar');
    await page.getByLabel('Usuario').fill('operador');
    await page.getByLabel('Contraseña').fill('no-es-la-clave');
    await page.getByRole('button', { name: 'Ingresar' }).click();
    await expect(page.getByRole('alert')).toHaveText('Usuario o contraseña incorrectos');
  });
});
