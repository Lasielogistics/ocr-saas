import { test, expect } from '@playwright/test';

test('add Nike shoes to cart on Amazon', async ({ page }) => {
  const cartItems: string[] = [];

  // Navigate to Amazon and search
  await page.goto('https://www.amazon.com', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  for (let i = 0; i < 3; i++) {
    // Search for Nike shoes
    await page.fill('#twotabsearchtextbox', 'Nike shoes');
    await page.click('#nav-search-submit-button');
    await page.waitForTimeout(3000);

    // Click on product (skip first i items to get different ones)
    const productLink = page.locator('[data-component-type="s-search-result"]').nth(i).locator('a').first();
    await productLink.click();
    await page.waitForTimeout(2000);

    try {
      await page.locator('#add-to-cart-button, #submit\\.add-to-cart').first().click({ timeout: 3000 });
    } catch {
      await page.locator('#add-to-cart-button').click();
    }
    await page.waitForTimeout(1000);

    const title = await page.title();
    cartItems.push(title.split(' ').slice(0, 3).join(' '));
    console.log(`Added item ${i + 1}: ${cartItems[i]}`);

    // Go back to search again
    await page.goto('https://www.amazon.com/s?k=Nike+shoes', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
  }

  console.log(`Successfully added ${cartItems.length} items to cart`);
  console.log('Items:', cartItems);
});