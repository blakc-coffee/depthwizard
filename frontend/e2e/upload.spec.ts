import { test, expect } from '@playwright/test';

test.describe('Input / Upload Screen', () => {
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

  test('Input page renders upload dropzone and format guidance', async ({ page }) => {
    await page.goto('/app');
    await expect(page).toHaveTitle('DepthWizard | New Terrain Job');
    await expect(
      page.getByRole('heading', { name: /input satellite \/ aerial imagery/i })
    ).toBeVisible();
    await expect(page.getByText(/drag and drop your image here/i)).toBeVisible();
    await expect(page.getByText(/format specifications:/i)).toBeVisible();
    await expect(page.getByRole('contentinfo')).toBeVisible(); // Footer check
  });

  test('file input is accessible and accepts supported files', async ({ page }) => {
    await page.goto('/app');

    const buffer = Buffer.from('fake image binary content');

    await page.setInputFiles('#file-upload', {
      name: 'sample_terrain.png',
      mimeType: 'image/png',
      buffer,
    });

    await expect(page.getByText('sample_terrain.png')).toBeVisible();
    await expect(page.getByText('PNG Image')).toBeVisible();
    await expect(page.getByText(/size:/i)).toBeVisible();
  });

  test('user can remove and change selected file', async ({ page }) => {
    await page.goto('/app');
    const buffer = Buffer.from('fake image content');

    await page.setInputFiles('#file-upload', {
      name: 'test_image.jpg',
      mimeType: 'image/jpeg',
      buffer,
    });

    await expect(page.getByText('test_image.jpg')).toBeVisible();

    await page.getByRole('button', { name: /remove file/i }).click();

    await expect(page.getByText(/drag and drop your image here/i)).toBeVisible();
  });

  test('submitting a valid file navigates to /processing/:jobId', async ({ page }) => {
    await page.goto('/app');
    const buffer = Buffer.from('fake image content');

    await page.setInputFiles('#file-upload', {
      name: 'elevation_map.tif',
      mimeType: 'image/tiff',
      buffer,
    });

    await page.getByRole('button', { name: /process image/i }).click();

    await page.waitForURL(/\/processing\/mock-job-/);
    await expect(page).toHaveTitle('DepthWizard | Processing Job');
  });

  test('displays recovery error banner when backend returns FILE_TOO_LARGE API error', async ({
    page,
  }) => {
    await page.goto('/app');
    const buffer = Buffer.from('fake image content');

    await page.setInputFiles('#file-upload', {
      name: 'too_large_raster.png',
      mimeType: 'image/png',
      buffer,
    });

    await page.getByRole('button', { name: /process image/i }).click();

    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByText(/File exceeds the maximum upload limit/i)).toBeVisible();
  });

  test('dropzone is keyboard operable', async ({ page }) => {
    await page.goto('/app');
    const dropzone = page.getByRole('button', {
      name: /upload satellite or aerial image file/i,
    });

    await expect(dropzone).toBeVisible();
    await dropzone.focus();
    await expect(dropzone).toBeFocused();
  });

  test('dual imagery inputs: user can select both primary baseline and optional secondary event files', async ({
    page,
  }) => {
    await page.goto('/app');

    // Input 1: Primary baseline file
    const primaryBuffer = Buffer.from('baseline image content');
    await page.setInputFiles('#file-upload', {
      name: 'pre_disaster_base.tif',
      mimeType: 'image/tiff',
      buffer: primaryBuffer,
    });

    await expect(page.getByText('pre_disaster_base.tif')).toBeVisible();
    await expect(page.getByText('Input 1 · Baseline')).toBeVisible();

    // Input 2: Secondary event file (optional)
    const secondaryBuffer = Buffer.from('event image content');
    await page.setInputFiles('#file-upload-secondary', {
      name: 'post_disaster_event.png',
      mimeType: 'image/png',
      buffer: secondaryBuffer,
    });

    await expect(page.getByText('post_disaster_event.png')).toBeVisible();
    await expect(page.getByText('Dual Comparison Mode Active')).toBeVisible();
    await expect(page.getByRole('button', { name: /process both images/i })).toBeVisible();

    await page.screenshot({ path: 'e2e-screenshots/07-dual-input-with-image-icons.png', fullPage: true });

    // Remove secondary file independently
    await page.getByRole('button', { name: 'Remove', exact: true }).click();
    await expect(page.getByText('post_disaster_event.png')).not.toBeVisible();
    await expect(page.getByText('pre_disaster_base.tif')).toBeVisible();
    await expect(page.getByRole('button', { name: /process image/i })).toBeVisible();
  });
});
