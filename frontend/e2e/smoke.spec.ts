import { test, expect } from '@playwright/test';

test('application loads and mounts successfully', async ({ page }) => {
  await page.goto('/');
  await page.waitForURL('/login');
  await expect(page.getByText('DepthWizard').first()).toBeVisible();
});
