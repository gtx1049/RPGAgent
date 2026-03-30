const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  page.on('console', msg => console.log('Browser console:', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('Page error:', err.message));
  
  // Handle dialog events (for the player name prompt)
  page.on('dialog', async dialog => {
    console.log('Dialog detected:', dialog.type(), dialog.message());
    if (dialog.type() === 'prompt') {
      await dialog.accept('测试玩家');
    } else {
      await dialog.dismiss();
    }
  });
  
  console.log('Opening page...');
  await page.goto('http://43.134.81.228:8080/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
  console.log('Page loaded');
  
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_01_initial.png' });
  
  // Check WS status before
  const wsStatusBefore = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status before:', wsStatusBefore);
  
  // Click the first game card using JavaScript
  console.log('\\nClicking first game card...');
  await page.evaluate(() => {
    const cards = document.querySelectorAll('.game-card');
    if (cards.length > 0) {
      console.log('Clicking card:', cards[0].querySelector('.game-name').textContent);
      cards[0].click();
    }
  });
  
  // Wait for the dialog to be handled and game to start
  await page.waitForTimeout(5000);
  
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_02_after_click.png' });
  
  // Check WS status after
  const wsStatusAfter = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status after:', wsStatusAfter);
  
  // Check if game-select overlay is still visible
  const gameSelectDisplay = await page.$eval('#game-select', el => window.getComputedStyle(el).display).catch(() => 'not found');
  console.log('Game select display:', gameSelectDisplay);
  
  // Check narrative
  const narrativeText = await page.$eval('#narrative', el => el.textContent.trim().substring(0, 300)).catch(() => 'not found');
  console.log('Narrative:', narrativeText);
  
  // Check scene title
  const sceneTitle = await page.$eval('#scene-title', el => el.textContent).catch(() => 'not found');
  console.log('Scene title:', sceneTitle);
  
  // Now test WebSocket disconnect
  console.log('\\n--- Testing WebSocket Disconnect ---');
  
  // Set offline mode
  console.log('Setting offline mode...');
  await context.setOffline(true);
  await page.waitForTimeout(2000);
  
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_03_offline.png' });
  
  const wsStatusOffline = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status offline:', wsStatusOffline);
  
  const narrativeOffline = await page.$eval('#narrative', el => el.textContent.trim().substring(0, 300)).catch(() => 'not found');
  console.log('Narrative after disconnect:', narrativeOffline);
  
  // Try clicking an action button while offline
  const actionBtns = await page.$$('.action-btn');
  console.log('Action buttons found:', actionBtns.length);
  
  if (actionBtns.length > 0) {
    const firstBtnText = await actionBtns[0].textContent();
    console.log('Clicking action button:', firstBtnText);
    
    try {
      await actionBtns[0].click({ timeout: 5000 });
      await page.waitForTimeout(2000);
      await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_04_offline_click.png' });
      
      const narrativeAfterClick = await page.$eval('#narrative', el => el.textContent.trim().substring(0, 300)).catch(() => 'not found');
      console.log('Narrative after offline click:', narrativeAfterClick);
    } catch (e) {
      console.log('Click failed:', e.message.substring(0, 200));
    }
  }
  
  // Re-enable online mode
  console.log('\\n--- Testing Reconnection ---');
  console.log('Re-enabling online mode...');
  await context.setOffline(false);
  await page.waitForTimeout(5000);
  
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_05_reconnected.png' });
  
  const wsStatusFinal = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status final:', wsStatusFinal);
  
  const narrativeFinal = await page.$eval('#narrative', el => el.textContent.trim().substring(0, 300)).catch(() => 'not found');
  console.log('Final narrative:', narrativeFinal);
  
  await browser.close();
  console.log('\\nTest complete');
})();
