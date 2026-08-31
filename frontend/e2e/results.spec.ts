import { test, expect } from '@playwright/test';

test.describe('Results Screen & 3D Terrain Viewer', () => {
  test.beforeEach(async ({ page }) => {
    // Inject mock session into localStorage before navigation
    await page.addInitScript(() => {
      const mockSession = {
        access_token: 'mock-token',
        token_type: 'bearer',
        expires_in: 3600,
        refresh_token: 'mock-refresh',
        user: {
          id: 'test-user-id',
          email: 'engineer@spatial.io',
          aud: 'authenticated',
          role: 'authenticated',
        },
      };
      localStorage.setItem('depthwizard_mock_session', JSON.stringify(mockSession));
    });
  });

  test('Absolute DSM results page displays metres, metrics, previews, and download button', async ({
    page,
  }) => {
    await page.goto('/results/mock-absolute-job-1234');
    await expect(page).toHaveTitle('DepthWizard | Terrain Results');
    await expect(
      page.getByRole('heading', { name: /terrain reconstruction/i })
    ).toBeVisible();

    // Check Absolute DSM badge
    await expect(page.getByText('Absolute DSM')).toBeVisible();

    // Check metres unit label
    await expect(page.getByText(/0.0 – 69.3 m/i)).toBeVisible();

    // Check image previews
    await expect(page.getByAltText(/original rgb texture preview/i)).toBeVisible();
    await expect(page.getByAltText(/decoded heightmap preview/i)).toBeVisible();

    // Check Download DSM button
    await expect(
      page.getByRole('link', { name: /download dsm/i })
    ).toBeVisible();

    // Check 3D Viewer overlay controls
    await expect(page.getByRole('button', { name: /normal/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /reset view/i })).toBeVisible();
  });

  test('Relative DSM results page displays relative units, warnings, N/A metrics, and unavailable DSM', async ({
    page,
  }) => {
    await page.goto('/results/mock-relative-job-5678');

    // Check Relative DSM badge
    await expect(page.getByText('Relative DSM')).toBeVisible();

    // Check relative units (and absence of 'm' label for height range)
    await expect(page.getByText(/0.0 – 255.0 relative/i)).toBeVisible();

    // Verify 'm' unit is NOT displayed for elevation range
    await expect(page.getByText(/255.0 m/i)).not.toBeVisible();

    // Check warnings banner
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByText(/no geo-metadata on this input/i)).toBeVisible();

    // Check DSM unavailable notice
    await expect(page.getByText(/dsm geotiff unavailable/i)).toBeVisible();
  });

  test('Mobile viewport layout renders without horizontal overflow and without inner scrollbar', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 }); // Mobile iPhone SE viewport
    await page.goto('/results/mock-absolute-job-1234');

    await expect(
      page.getByRole('heading', { name: /terrain reconstruction/i })
    ).toBeVisible();

    // Verify page container scroll width does not exceed client width
    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(overflow).toBe(false);

    // Verify summary panel has NO inner scrollbar (overflow-y is not auto/scroll)
    const hasInnerScrollbar = await page.evaluate(() => {
      const summaryPanel = document.querySelector('.lg\\:w-auto');
      if (!summaryPanel) return false;
      const style = window.getComputedStyle(summaryPanel);
      return style.overflowY === 'auto' || style.overflowY === 'scroll';
    });
    expect(hasInnerScrollbar).toBe(false);
  });

  test('Desktop viewport (1440px) renders full available workspace layout', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/results/mock-absolute-job-1234');

    await expect(
      page.getByRole('heading', { name: /terrain reconstruction/i })
    ).toBeVisible();

    // Verify main content container uses full desktop workspace width (> 1300px)
    const mainWidth = await page.evaluate(() => {
      const main = document.querySelector('main');
      return main ? main.clientWidth : 0;
    });
    expect(mainWidth).toBeGreaterThan(1300);

    // Verify zero horizontal overflow at 1440px
    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(overflow).toBe(false);
  });
});
