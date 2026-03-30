const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  // Enable console logging
  page.on('console', msg => console.log('Browser console:', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('Page error:', err.message));
  
  console.log('Opening page...');
  await page.goto('http://43.134.81.228:8080/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  console.log('Page loaded');
  
  // Take screenshot of initial state
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_01_initial.png' });
  console.log('Screenshot 1 saved');
  
  // Check WS status before clicking
  const wsStatusBefore = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status before:', wsStatusBefore);
  
  // Check what's visible
  const gameSelectDisplay = await page.$eval('#game-select', el => window.getComputedStyle(el).display).catch(() => 'not found');
  console.log('Game select display:', gameSelectDisplay);
  
  // Try clicking on the game card with force option
  console.log('Looking for game cards...');
  const gameCards = await page.$$('.game-card');
  console.log('Found', gameCards.length, 'game cards');
  
  if (gameCards.length > 0) {
    const gameName = await gameCards[0].$eval('.game-name', el => el.textContent);
    console.log('First game:', gameName);
    
    console.log('Clicking first game card with force...');
    await gameCards[0].click({ force: true });
    await page.waitForTimeout(3000);
    console.log('Clicked and waited');
    
    // Take screenshot after clicking
    await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_02_after_click.png' });
    console.log('Screenshot 2 saved');
    
    // Check if game-select overlay is still visible
    const gameSelectVisible = await page.$eval('#game-select', el => {
      const style = window.getComputedStyle(el);
      return style.display !== 'none' && style.visibility !== 'hidden';
    }).catch(() => false);
    console.log('Game select overlay still visible:', gameSelectVisible);
    
    // Check WS status after game start
    const wsStatusAfter = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
    console.log('WS Status after:', wsStatusAfter);
    
    // Check narrative panel for content
    const narrativeText = await page.$eval('#narrative', el => el.textContent.trim().substring(0, 200)).catch(() => 'not found');
    console.log('Narrative:', narrativeText);
    
    // Check if action buttons are visible and enabled
    const actionBtns = await page.$$('.action-btn');
    console.log('Action buttons found:', actionBtns.length);
    
    if (actionBtns.length > 0) {
      const firstBtnText = await actionBtns[0].textContent();
      const firstBtnEnabled = await actionBtns[0].isEnabled();
      console.log('First action button:', firstBtnText, 'enabled:', firstBtnEnabled);
    }
    
    // Check scene title
    const sceneTitle = await page.$eval('#scene-title', el => el.textContent).catch(() => 'not found');
    console.log('Scene title:', sceneTitle);
  }
  
  await browser.close();
  console.log('\\nInitial investigation complete');
})();
