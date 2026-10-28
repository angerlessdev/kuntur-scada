import { expect, test } from '@playwright/test';

import { Field, signIn } from './support';

/**
 * The screenshots in the README, taken from the running platform: `npm run screenshots`.
 * They stage a real incident through the simulator, so the pictures show the system working.
 */
const OUT = process.env.KUNTUR_SCREENSHOTS_DIR ?? '../docs/img';

test('capturas de la documentación', async ({ page, request }) => {
  const field = new Field(request);
  await page.goto('/ingresar');
  await page.screenshot({ path: `${OUT}/ingreso.png` });

  await signIn(page, 'operador');
  await field.conditions('ups-sur-01', { ambient_c: 48 });
  await field.fault('barrera-sur-01', 'DOWN');
  try {
    await expect(page.getByText('crítica', { exact: false }).first()).toBeVisible({ timeout: 60_000 });
    // The hot battery's alert, confirmed by the rule (not just an amber pointer), on its tile
    await expect(page.locator('kt-device-tile .tile[data-level="warning"]').first()).toBeVisible({
      timeout: 150_000,
    });
    await page.screenshot({ path: `${OUT}/flota.png`, fullPage: true });

    await page.getByRole('link', { name: 'Alertas' }).click();
    await expect(page.getByRole('heading', { name: 'Causas probables', exact: false })).toBeVisible();
    await page.screenshot({ path: `${OUT}/alertas.png`, fullPage: true });

    await page.goto('/equipos/ups-sur-01');
    await expect(page.getByRole('heading', { name: 'Tendencia' })).toBeVisible();
    await page.getByRole('button', { name: 'Explicar la alerta' }).first().click();
    await expect(page.getByRole('heading', { name: 'Qué revisar, en este orden' })).toBeVisible();
    await page.waitForTimeout(1500); // let the chart draw
    await page.screenshot({ path: `${OUT}/equipo.png`, fullPage: true });
  } finally {
    await field.fault('barrera-sur-01', 'NONE');
    await field.conditions('ups-sur-01', { ambient_c: 31 });
  }
});
