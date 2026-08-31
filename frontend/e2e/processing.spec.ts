import { test, expect } from '@playwright/test';

test.describe('Processing Screen', () => {
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

  test('navigating to /processing/:jobId renders the processing screen and stage status', async ({
    page,
  }) => {
    await page.goto('/processing/mock-processing-job-1');
    await expect(page).toHaveTitle('DepthWizard | Processing Job');
    await expect(
      page.getByRole('heading', { name: /terrain reconstruction pipeline/i })
    ).toBeVisible();

    // Verify stage label mapping and progress bar element
    await expect(page.getByText(/estimating depth…/i)).toBeVisible();

    const progressBar = page.getByRole('progressbar', { name: /processing progress/i });
    await expect(progressBar).toBeVisible();
    await expect(progressBar).toHaveAttribute('aria-valuenow', '40');

    // Verify accessible stage status region
    const liveRegion = page.locator('[aria-live="polite"]');
    await expect(liveRegion).toBeVisible();
  });

  test('completed status automatically navigates to /results/:jobId', async ({ page }) => {
    // mock-job-completed-immediate will hit mockGetJob fallback which returns completed immediately
    await page.goto('/processing/mock-job-completed-immediate');

    // Should navigate to /results/mock-job-completed-immediate
    await page.waitForURL(/\/results\/mock-job-completed-immediate/);
    await expect(page).toHaveTitle('DepthWizard | Terrain Results');
  });

  test('failed status displays error details and recovery button to return to workspace', async ({
    page,
  }) => {
    await page.goto('/processing/mock-failed-job-999');

    // Check error banner and message
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(
      page.getByText(/SRTM reference elevation fetch failed for input coordinates/i)
    ).toBeVisible();

    // Click Return to Workspace button
    const returnBtn = page.getByRole('button', { name: /return to workspace/i });
    await expect(returnBtn).toBeVisible();
    await returnBtn.click();

    // Verify navigation back to /app
    await page.waitForURL('/app');
    await expect(page).toHaveTitle('DepthWizard | New Terrain Job');
  });
});
