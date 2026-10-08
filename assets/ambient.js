// Convection-inspired soft fields, not a physical fluid simulation.
// A fresh per-load seed changes the initial arrangement without restarting on resize.
// This canvas covers the opening section and its fading lower edge only.
window.createCvAmbient = function createCvAmbient(canvas, hero) {
  const context = canvas.getContext('2d', { alpha: true });
  if (!context) return { setRunning() {} };
  const seed = window.crypto?.getRandomValues
    ? window.crypto.getRandomValues(new Uint32Array(1))[0]
    : Math.floor(Math.random() * 4294967296);
  let running = false;
  let visible = false;
  let frame = 0;
  let last = 0;
  let time = (seed / 4294967296) * 240;
  let width = 0;
  let height = 0;
  let pixels;
  let density;
  let red;
  let green;
  let blue;

  const mix = (a, b, t) => a + (b - a) * t;
  const smooth = value => {
    const t = Math.max(0, Math.min(1, value));
    return t * t * (3 - 2 * t);
  };
  const hash = (x, y, z) => {
    let n = seed ^ Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 2147483647);
    n = Math.imul(n ^ (n >>> 13), 1274126177);
    return ((n ^ (n >>> 16)) >>> 0) / 4294967295;
  };
  const noise = (x, y, z) => {
    const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
    const sx = smooth(x - ix), sy = smooth(y - iy), sz = smooth(z - iz);
    const slice = dz => mix(
      mix(hash(ix, iy, iz + dz), hash(ix + 1, iy, iz + dz), sx),
      mix(hash(ix, iy + 1, iz + dz), hash(ix + 1, iy + 1, iz + dz), sx), sy
    );
    return mix(slice(0), slice(1), sz);
  };
  const colors = [[152, 40, 101], [91, 57, 158], [29, 108, 121]];
  const parcels = Array.from({ length: 10 }, (_, i) => ({
    id: i,
    x: .12 + hash(i, 3, 9) * .76,
    y: -.04 + hash(i, 7, 2) * 1.08,
    vx: 0,
    vy: i < 8 ? -.065 : .035,
    rising: i < 8,
    radius: .095 + hash(i, 1, 4) * .065,
    speed: .052 + hash(i, 5, 6) * .045,
    color: colors[i < 8 ? i % 2 : 2],
    cycle: 0
  }));
  const advance = dt => {
    time += dt;
    for (const p of parcels) {
      const x = p.x * 1.7, y = p.y * 1.6, z = time * .1;
      const e = .025;
      const curlX = (noise(x, y + e, z) - noise(x, y - e, z)) / (2 * e);
      const curlY = -(noise(x + e, y, z) - noise(x - e, y, z)) / (2 * e);
      const edge = p.x < .1 ? (.1 - p.x) * .22 : p.x > .9 ? (.9 - p.x) * .22 : 0;
      const targetX = curlX * .033 + edge;
      const targetY = (p.rising ? -p.speed : p.speed * .5) + curlY * .011;
      p.vx = mix(p.vx, targetX, Math.min(1, dt * 1.3));
      p.vy = mix(p.vy, targetY, Math.min(1, dt * 1.3));
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      if ((p.rising && p.y < -.6) || (!p.rising && p.y > 1.6)) {
        p.cycle += 1;
        p.x = .12 + hash(p.id, p.cycle, 11) * .76;
        p.y = p.rising ? 1.6 : -.6;
      }
    }
  };
  const paint = () => {
    if (!pixels) return;
    density.fill(0); red.fill(0); green.fill(0); blue.fill(0);
    for (const p of parcels) {
      const shape = noise(p.id + 2, time * .11, 5) - .5;
      const rx = p.radius * (1 + shape * .28);
      const ry = p.radius * 1.45 * (1 - shape * .24);
      const left = Math.max(0, Math.floor((p.x - rx * 2) * width));
      const right = Math.min(width - 1, Math.ceil((p.x + rx * 2) * width));
      const top = Math.max(0, Math.floor((p.y - ry * 2) * height));
      const bottom = Math.min(height - 1, Math.ceil((p.y + ry * 2) * height));
      for (let y = top; y <= bottom; y++) {
        const dy = (y / height - p.y) / ry;
        for (let x = left; x <= right; x++) {
          const dx = (x / width - p.x) / rx;
          const kernel = 1 - (dx * dx + dy * dy) / 4;
          if (kernel <= 0) continue;
          const weight = kernel * kernel * kernel;
          const i = y * width + x;
          density[i] += weight;
          red[i] += weight * p.color[0];
          green[i] += weight * p.color[1];
          blue[i] += weight * p.color[2];
        }
      }
    }
    const data = pixels.data;
    for (let i = 0; i < density.length; i++) {
      const field = density[i];
      const j = i * 4;
      if (field < .001) {
        data[j + 3] = 0;
        continue;
      }
      data[j] = red[i] / field;
      data[j + 1] = green[i] / field;
      data[j + 2] = blue[i] / field;
      data[j + 3] = smooth((field - .06) / 1.15) * 142;
    }
    context.putImageData(pixels, 0, 0);
    canvas.hidden = false;
  };
  const header = document.querySelector('.site-header');
  const resize = () => {
    const overlap = header?.offsetHeight || 90;
    hero.style.setProperty('--ambient-overlap', `${overlap}px`);
    const bounds = canvas.parentElement.getBoundingClientRect();
    const nextWidth = hero.clientWidth < 600 ? 96 : 144;
    const nextHeight = Math.max(64, Math.min(240, Math.round(nextWidth * bounds.height / Math.max(1, bounds.width))));
    if (width === nextWidth && height === nextHeight) return;
    width = nextWidth; height = nextHeight;
    canvas.width = width; canvas.height = height;
    pixels = context.createImageData(width, height);
    density = new Float32Array(width * height);
    red = new Float32Array(width * height);
    green = new Float32Array(width * height);
    blue = new Float32Array(width * height);
    paint();
  };
  const tick = now => {
    if (!running || !visible) { frame = 0; return; }
    if (!last) last = now;
    if (now - last >= 50) {
      advance(Math.min((now - last) / 1000, .12));
      last = now;
      paint();
    }
    frame = requestAnimationFrame(tick);
  };
  const sync = () => {
    if (running && visible) {
      if (!frame) { last = 0; frame = requestAnimationFrame(tick); }
    } else {
      cancelAnimationFrame(frame);
      frame = 0; last = 0;
    }
  };
  resize();
  if ('ResizeObserver' in window) {
    const observer = new ResizeObserver(resize);
    observer.observe(hero);
    if (header) observer.observe(header);
  } else window.addEventListener('resize', resize, { passive: true });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      visible = entries[0].isIntersecting;
      sync();
    }).observe(canvas.parentElement);
  }
  return { setRunning(enabled) { running = enabled; sync(); } };
};
