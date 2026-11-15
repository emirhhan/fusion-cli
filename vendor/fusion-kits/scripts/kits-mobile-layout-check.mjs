/** Dar ekranda gerçek yerleşim, menü odağı ve gezinme regresyonları. */
export async function checkMobileLayout(
  page,
  base,
  spaceId,
  pageId,
  screenshot,
) {
  const viewport = page.viewportSize();
  const overlap = (a, b) =>
    a.x < b.x + b.width &&
    b.x < a.x + a.width &&
    a.y < b.y + b.height &&
    b.y < a.y + a.height;
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const [name, path] of [
      ['home', ''],
      ['library', `/#/spaces/${spaceId}`],
      ['editor', `/#/spaces/${spaceId}/pages/${pageId}`],
    ]) {
      await page.goto(base + path);
      const menu = page.getByRole('button', { name: 'Menüyü aç', exact: true });
      await menu.waitFor();
      if (name === 'editor')
        await page.locator('[contenteditable="true"]').waitFor();
      const controls = page.locator(
        '.topbar .breadcrumbs, .topbar button:visible',
      );
      const boxes = (
        await Promise.all(
          (await controls.all()).map((item) => item.boundingBox()),
        )
      ).filter(Boolean);
      const hamburger = await menu.boundingBox();
      for (const box of boxes)
        if (
          box !== hamburger &&
          overlap(hamburger, box) &&
          (box.x !== hamburger.x || box.y !== hamburger.y)
        )
          throw new Error(
            `${width}px ${name}: hamburger başlık veya araçla örtüşüyor.`,
          );
      for (let a = 0; a < boxes.length; a++)
        for (let b = a + 1; b < boxes.length; b++)
          if (overlap(boxes[a], boxes[b]))
            throw new Error(
              `${width}px ${name}: üst bar denetimleri örtüşüyor.`,
            );
      if (
        await page.evaluate(
          () =>
            globalThis.document.documentElement.scrollWidth >
            globalThis.innerWidth + 1,
        )
      )
        throw new Error(`${width}px ${name}: yatay taşma var.`);
      await screenshot(`kits-${name}-header-${width}`);
      await menu.click();
      const nav = page.locator('#workspace-sidebar.open');
      await nav.waitFor();
      const close = nav.getByRole('button', {
        name: 'Gezinmeyi kapat',
        exact: true,
      });
      await close.waitFor();
      await screenshot(`kits-${name}-menu-${width}`);
      await close.focus();
      await page.keyboard.press('Shift+Tab');
      if (
        !(await nav.evaluate((element) =>
          element.contains(globalThis.document.activeElement),
        ))
      )
        throw new Error('Menü odağı arka plana kaçtı.');
      await page.keyboard.press('Escape');
      await page.waitForFunction(
        () => !globalThis.document.querySelector('#workspace-sidebar.open'),
      );
      if (
        !(await menu.evaluate(
          (element) => element === globalThis.document.activeElement,
        ))
      )
        throw new Error('Menü kapanınca odak açıcıya dönmedi.');
      if (name === 'home') {
        await menu.click();
        await nav
          .getByRole('button', { name: 'Ayarlar ve bağlantılar', exact: true })
          .click();
        const dialog = page.locator('section[role="dialog"]');
        await dialog.waitFor();
        const paletteMatches = await dialog.evaluate((element) => {
          const probe = globalThis.document.createElement('span');
          probe.style.backgroundColor = 'var(--kits-dialog-surface)';
          element.append(probe);
          const expected = globalThis.getComputedStyle(probe).backgroundColor;
          probe.remove();
          return (
            globalThis.getComputedStyle(element).backgroundColor === expected
          );
        });
        if (!paletteMatches)
          throw new Error(
            'Ayar penceresi marka yüzeyi tema tarafından ezildi.',
          );
        if (await page.locator('#workspace-sidebar.open').count())
          throw new Error('Dialog açılınca çekmece açık kaldı.');
        await page.keyboard.press('Tab');
        if (
          !(await dialog.evaluate((element) =>
            element.contains(globalThis.document.activeElement),
          ))
        )
          throw new Error('Dialog odağı çekmeceye kaçtı.');
        await page.keyboard.press('Shift+Tab');
        if (
          !(await dialog.evaluate((element) =>
            element.contains(globalThis.document.activeElement),
          ))
        )
          throw new Error('Dialog ters Tab odağı kaçtı.');
        await screenshot(`kits-settings-dialog-mobile-${width}`);
        await page.keyboard.press('Escape');
        await page.waitForFunction(
          () => !globalThis.document.querySelector('[role="dialog"]'),
        );
        if (await page.locator('#workspace-sidebar.open').count())
          throw new Error('Escape arkadaki çekmeceyi yeniden açtı.');
        if (
          !(await menu.evaluate(
            (element) => element === globalThis.document.activeElement,
          ))
        )
          throw new Error('Dialog kapanınca odak menü açıcıya dönmedi.');
      }
    }
  }
  await page.setViewportSize(viewport);
  return 'mobile-320-390-home-library-editor-header-no-overlap-menu-focus-escape';
}
