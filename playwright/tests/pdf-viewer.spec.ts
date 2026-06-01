import { test, expect } from '@playwright/test';

test('PDF viewer has text layer for selection', async ({ page }) => {
  // Go to OCR review page
  await page.goto('http://192.168.50.100:3000/ocr_review.html');
  
  // Wait for table to load
  await page.waitForSelector('#review-tbody tr.doc-row', { timeout: 15000 });
  await page.waitForTimeout(2000);
  
  // Debug: count rows and check visibility
  const rowCount = await page.locator('#review-tbody tr.doc-row').count();
  console.log('Doc rows found:', rowCount);
  
  // Check if rows are visible
  if (rowCount > 0) {
    const firstRowVisible = await page.locator('#review-tbody tr.doc-row').first().isVisible();
    console.log('First row visible:', firstRowVisible);
  }
  
  // Take screenshot for debugging
  await page.screenshot({ path: 'test-results/debug.png' });
  console.log('Screenshot saved');
  
  // Get page content
  const html = await page.content();
  console.log('Page has review-tbody:', html.includes('review-tbody'));
  
  // Click using JavaScript instead
  await page.evaluate(() => {
    const btn = document.querySelector('#review-tbody tr.doc-row button[title="View PDF"]') as HTMLButtonElement;
    if (btn) btn.click();
    else console.error('Button not found');
  });
  
  await page.waitForTimeout(4000);
  
  // Take screenshot after click
  await page.screenshot({ path: 'test-results/debug2.png' });
  
  // Check modal
  const modalClass = await page.locator('#pdf-modal').getAttribute('class');
  console.log('Modal class:', modalClass);
  
  const canvas = await page.locator('#pdf-canvas-standalone').isVisible();
  console.log('Canvas visible:', canvas);
  
  const canvasWidth = await page.locator('#pdf-canvas-standalone').getAttribute('width');
  console.log('Canvas width:', canvasWidth);
  
  const textLayerCount = await page.locator('#pdf-canvas-container-standalone .text-layer span').count();
  console.log('Text spans:', textLayerCount);
});
