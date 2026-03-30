const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  // Monitor WebSocket connections
  const webSocketConnections = [];
  page.on('websocket', ws => {
    console.log('WebSocket opened:', ws.url());
    webSocketConnections.push(ws.url());
    ws.on('framesent', frame => console.log('WS sent:', frame.payload));
    ws.on('framereceived', frame => console.log('WS received:', frame.payload));
    ws.on('close', () => console.log('WebSocket closed'));
  });
  
  // Monitor all network requests
  page.on('request', request => {
    if (request.url().includes('ws') || request.url().includes('socket')) {
      console.log('Socket request:', request.url());
    }
  });
  
  page.on('response', response => {
    if (response.url().includes('ws') || response.url().includes('socket')) {
      console.log('Socket response:', response.url(), response.status());
    }
  });
  
  console.log('Opening page...');
  await page.goto('http://43.134.81.228:8080/', { waitUntil: 'domcontentloaded' });
  console.log('Page loaded, waiting for WS...');
  
  await page.waitForTimeout(5000);
  
  // Check WS status
  const wsStatus = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status:', wsStatus);
  
  // Check for any pending connections
  console.log('WebSocket connections so far:', webSocketConnections.length);
  
  // Try to look at the game initialization
  const gameInitState = await page.evaluate(() => {
    // Check if there's any game state object
    return {
      hasGameSelect: !!document.querySelector('#game-select'),
      gameCardCount: document.querySelectorAll('.game-card').length,
      gameListVisible: window.getComputedStyle(document.querySelector('#game-list')).display,
      gameSelectPointerEvents: window.getComputedStyle(document.querySelector('#game-select')).pointerEvents
    };
  });
  console.log('Game init state:', JSON.stringify(gameInitState));
  
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_ws_01.png' });
  
  // Try clicking the first game card and waiting for WS
  console.log('\\nClicking first game card...');
  await page.evaluate(() => {
    document.querySelectorAll('.game-card')[0].click();
  });
  
  // Wait for potential WS activity
  await page.waitForTimeout(5000);
  
  // Check again
  const wsStatusAfter = await page.$eval('#ws-status', el => el.textContent).catch(() => 'not found');
  console.log('WS Status after click:', wsStatusAfter);
  
  console.log('WebSocket connections after click:', webSocketConnections.length);
  
  await page.screenshot({ path: '/root/.openclaw/workspace/RPGAgent/playwright_ws_02.png' });
  
  await browser.close();
  console.log('\\nTest complete');
})();
