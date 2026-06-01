import { test, expect } from '@playwright/test';

test.describe('TERMPoint Auto-Book Panel', () => {

  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('http://192.168.50.100/login.html');
    const loginBtn = page.locator('#login-btn');
    if (await loginBtn.isVisible()) {
      await loginBtn.click();
      await page.waitForTimeout(2000);
    }
    await page.goto('http://192.168.50.100/termpoint.html');
    // Wait for connect
    await page.waitForFunction(() => {
      const badge = document.getElementById('authBadge');
      return badge && badge.textContent !== 'CONNECTED';
    }, { timeout: 5000 }).catch(() => {});
    // Wait extra for connect to succeed
    await page.waitForTimeout(3000);
  });

  test('panel opens and has all three mode tabs', async ({ page }) => {
    // Open the auto-book panel
    await page.locator('#abToggle').click();
    await expect(page.locator('#abPanel')).toHaveClass(/open/);

    // Check Configure tab active by default
    await expect(page.locator('#abTabCfg')).toHaveClass(/active/);

    // Check mode tabs: First Available, Specific Slot, Time Range
    await expect(page.locator('#abTabFirst')).toBeVisible();
    await expect(page.locator('#abTabSlot')).toBeVisible();
    await expect(page.locator('#abTabRange')).toBeVisible();
  });

  test('First Available mode shows correct fields', async ({ page }) => {
    await page.locator('#abToggle').click();
    await expect(page.locator('#abTabFirst')).toHaveClass(/active/);

    // Check First Available specific fields
    await expect(page.locator('#abFirstFields')).toBeVisible();
    await expect(page.locator('#abFirstFromDate')).toBeVisible();
    await expect(page.locator('#abFirstToday')).toBeChecked();
    await expect(page.locator('#abFirstExact')).toBeChecked();

    // Specific Slot and Range should be hidden
    await expect(page.locator('#abSlotFields')).toBeHidden();
    await expect(page.locator('#abRangeFields')).toBeHidden();
  });

  test('Specific Slot mode shows correct fields', async ({ page }) => {
    await page.locator('#abToggle').click();
    await page.locator('#abTabSlot').click();

    await expect(page.locator('#abSlotFields')).toBeVisible();
    await expect(page.locator('#abTargetDate')).toBeVisible();
    await expect(page.locator('#abTargetTime')).toBeVisible();
    await expect(page.locator('#abAcceptEarlier')).toBeVisible();

    await expect(page.locator('#abFirstFields')).toBeHidden();
    await expect(page.locator('#abRangeFields')).toBeHidden();
  });

  test('Time Range mode shows correct fields', async ({ page }) => {
    await page.locator('#abToggle').click();
    await page.locator('#abTabRange').click();

    await expect(page.locator('#abRangeFields')).toBeVisible();
    await expect(page.locator('#abFromDate')).toBeVisible();
    await expect(page.locator('#abToDate')).toBeVisible();
    await expect(page.locator('#abCheckEarlier')).toBeVisible();
  });

  test('Pending Searches tab shows empty state and count badge', async ({ page }) => {
    await page.locator('#abToggle').click();

    // Click Pending Searches tab
    await page.locator('#abTabSearches').click();
    await expect(page.locator('#abSearchesPane')).toBeVisible();

    // Should show empty state
    await expect(page.locator('#abPendingList')).toContainText('No active searches');

    // Count badge should be hidden when zero
    const badge = page.locator('#abPendingCount');
    await expect(badge).toBeHidden();
  });

  test('adding a search creates a search card', async ({ page }) => {
    await page.locator('#abToggle').click();

    // Fill in container and use First Available mode
    await page.locator('#abContainer').fill('TESTU1234567');
    await page.locator('#abMoveType').selectOption('MD');

    // Start search (button says "+ Add Search")
    await page.locator('#abStartBtn').click();

    // Pending searches tab should show badge with count
    await page.locator('#abTabSearches').click();
    const badge = page.locator('#abPendingCount');
    await expect(badge).toBeVisible();
    await expect(badge).toHaveText('1');

    // Should show a search card
    await expect(page.locator('#abPendingList')).toContainText('TESTU1234567');
    await expect(page.locator('#abPendingList')).toContainText('SEARCHING');
  });

  test('search card has stop and remove buttons', async ({ page }) => {
    await page.locator('#abToggle').click();

    await page.locator('#abContainer').fill('TESTU1234567');
    await page.locator('#abMoveType').selectOption('MD');
    await page.locator('#abStartBtn').click();

    // Switch to searches tab
    await page.locator('#abTabSearches').click();

    // Should show Stop button (since status is searching)
    await expect(page.locator('.btn-sc-stop').first()).toBeVisible();
    // Should show Remove button
    await expect(page.locator('.btn-sc-remove').first()).toBeVisible();
  });

  test('stop button changes status to stopped', async ({ page }) => {
    await page.locator('#abToggle').click();

    await page.locator('#abContainer').fill('TESTU1234567');
    await page.locator('#abMoveType').selectOption('MD');
    await page.locator('#abStartBtn').click();

    await page.locator('#abTabSearches').click();

    // Stop the search
    await page.locator('.btn-sc-stop').first().click();

    // Status should change to STOPPED
    await expect(page.locator('#abPendingList')).toContainText('STOPPED');
  });

  test('retry interval and exponential backoff options exist', async ({ page }) => {
    await page.locator('#abToggle').click();

    await expect(page.locator('#abRetryInterval')).toBeVisible();
    await expect(page.locator('#abExpBackoff')).toBeVisible();

    // Default should be 60 seconds
    const option = page.locator('#abRetryInterval option:checked');
    await expect(option).toHaveText('1 minute');
  });

  test('Configure and Pending Searches tabs switch correctly', async ({ page }) => {
    await page.locator('#abToggle').click();

    // Should start on Configure tab
    await expect(page.locator('#abCfgPane')).toBeVisible();
    await expect(page.locator('#abSearchesPane')).toBeHidden();

    // Switch to Pending Searches
    await page.locator('#abTabSearches').click();
    await expect(page.locator('#abCfgPane')).toBeHidden();
    await expect(page.locator('#abSearchesPane')).toBeVisible();

    // Switch back to Configure
    await page.locator('#abTabCfg').click();
    await expect(page.locator('#abCfgPane')).toBeVisible();
    await expect(page.locator('#abSearchesPane')).toBeHidden();
  });
});