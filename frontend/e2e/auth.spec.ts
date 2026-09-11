import { test, expect } from '@playwright/test';

test.describe('Authentication & Application Shell', () => {
  test('/login renders authentication form', async ({ page }) => {
    await page.goto('/login');
    await expect(page).toHaveTitle('DepthWizard | Sign In');
    await expect(page.getByRole('heading', { name: /sign in to depthwizard/i })).toBeVisible();
  });

  test('email and password fields are accessible by label', async ({ page }) => {
    await page.goto('/login');
    const emailInput = page.getByLabel('Email address');
    const passwordInput = page.getByLabel('Password');

    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(emailInput).toHaveAttribute('type', 'email');
    await expect(passwordInput).toHaveAttribute('type', 'password');
  });

  test('submit button is keyboard operable', async ({ page }) => {
    // Intercept Supabase token call so test is deterministic with or without live backend
    await page.route('**/auth/v1/token*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock-access-token',
          token_type: 'bearer',
          expires_in: 3600,
          refresh_token: 'mock-refresh-token',
          user: {
            id: 'mock-user-1234',
            aud: 'authenticated',
            role: 'authenticated',
            email: 'engineer@spatial.io',
          },
        }),
      });
    });

    await page.goto('/login');
    const emailInput = page.getByLabel('Email address');
    const passwordInput = page.getByLabel('Password');

    await emailInput.fill('engineer@spatial.io');
    await passwordInput.fill('password123');

    // Press Enter to submit form
    await passwordInput.press('Enter');

    // Expect redirect or mock sign in to complete
    await page.waitForURL('/app');
    await expect(page).toHaveTitle('DepthWizard | New Terrain Job');
  });

  test('unauthenticated /app redirects to /login', async ({ page }) => {
    await page.goto('/app');
    await page.waitForURL('/login');
    await expect(page.getByRole('heading', { name: /sign in to depthwizard/i })).toBeVisible();
  });

  test('authenticated session permits access to /app shell', async ({ page }) => {
    // Inject mock session into localStorage before navigation
    await page.addInitScript(() => {
      const mockSession = {
        access_token: 'mock-token',
        token_type: 'bearer',
        expires_in: 3600,
        refresh_token: 'mock-refresh',
        user: {
          id: 'test-user-id',
          email: 'test.engineer@spatial.io',
          aud: 'authenticated',
          role: 'authenticated',
        },
      };
      localStorage.setItem('depthwizard_mock_session', JSON.stringify(mockSession));
    });

    await page.goto('/app');
    await expect(page).toHaveTitle('DepthWizard | New Terrain Job');
    await expect(page.getByText('test.engineer@spatial.io')).toBeVisible();
    await expect(page.getByRole('button', { name: /sign out/i })).toBeVisible();
  });
});
