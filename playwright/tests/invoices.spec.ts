import { test, expect } from '@playwright/test';

test('invoices page loads and View button opens PDF modal', async ({ page }) => {
  const errors: string[] = [];
  page.on('console', m => {
    if (m.type() === 'error') errors.push(m.text());
  });

  // Login first
  await page.goto('http://192.168.50.100/login.html');
  await page.waitForLoadState('networkidle');
  // Values are pre-filled, just click login
  await page.click('#login-btn');
  await page.waitForTimeout(3000);

  // Navigate to invoices
  await page.goto('http://192.168.50.100/invoices.html');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);

  // Check title
  await expect(page).toHaveTitle(/Invoices/);

  // Check table loaded
  const rows = page.locator('#invoice-tbody tr[data-id]');
  await expect(rows.first()).toBeVisible({ timeout: 10000 });
  const rowCount = await rows.count();
  console.log('Invoice rows:', rowCount);
  expect(rowCount).toBeGreaterThan(0);

  // Summary cards
  const draftCount = await page.locator('#count-draft').textContent();
  console.log('Draft count:', draftCount);

  // Click View button on first invoice
  const viewBtn = page.locator('#invoice-tbody tr[data-id] .btn-secondary').first();
  await viewBtn.click();
  await page.waitForTimeout(3000);

  // Check PDF modal opened
  const pdfModal = page.locator('#pdf-modal');
  await expect(pdfModal).toHaveClass(/show/, { timeout: 5000 });
  console.log('PDF modal is open');

  // Check PDF loading or error state
  const loading = page.locator('#pdf-loading');
  const pdfCanvas = page.locator('#pdf-canvas');
  const pdfError = page.locator('#pdf-error');
  
  const isLoading = await loading.isVisible();
  const isError = await pdfError.isVisible();
  const isCanvas = await pdfCanvas.isVisible();
  
  console.log(`PDF state - loading: ${isLoading}, error: ${isError}, canvas: ${isCanvas}`);
  
  // Wait for PDF to render
  await page.waitForTimeout(5000);
  const isCanvasAfter = await pdfCanvas.isVisible();
  console.log(`PDF canvas visible after wait: ${isCanvasAfter}`);

  // Console errors check
  console.log('Console errors:', errors.length > 0 ? errors.join('; ') : 'none');
  
  // Close modal
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);
});
