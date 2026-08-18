// A small dependency-free force simulation for the symbol graph.
// Deliberate: zero external deps means the page works offline forever.
// Forces: pairwise repulsion, spring along edges, weak centering,
// positional collision (nodes never overlap); velocity damping; alpha
// decay. O(n²) repulsion is fine at ~700 nodes.

export function createSim(nodes, links, opts = {}) {
  const width = opts.width ?? 800;
  const height = opts.height ?? 600;
  const repulsion = opts.repulsion ?? 7500;
  const springK = opts.springK ?? 0.12;
  const restLen = opts.restLen ?? 150;
  const centerK = opts.centerK ?? 0.008;
  const damping = opts.damping ?? 0.6;
  const decay = opts.decay ?? 0.014;
  const collidePad = opts.collidePad ?? 10;

  let alpha = 1;
  const cx = width / 2;
  const cy = height / 2;

  // Deterministic phyllotaxis start so reloads look the same.
  nodes.forEach((n, i) => {
    if (n.x == null || n.y == null) {
      const a = i * 2.39996323;
      const r = 22 * Math.sqrt(i + 1);
      n.x = cx + r * Math.cos(a);
      n.y = cy + r * Math.sin(a);
    }
    n.vx = 0;
    n.vy = 0;
  });

  // Degree-normalized spring strength (d3's default): hubs pulled by many
  // springs would otherwise collapse the core into a knot.
  const linkDeg = new Map();
  for (const l of links) {
    linkDeg.set(l.source, (linkDeg.get(l.source) || 0) + 1);
    linkDeg.set(l.target, (linkDeg.get(l.target) || 0) + 1);
  }
  const springW = links.map(
    (l) => 1 / Math.min(linkDeg.get(l.source), linkDeg.get(l.target)));

  // Warm start: Laplacian smoothing pulls each node toward its neighbors'
  // centroid, so connected clusters begin together and the forces only have
  // to inflate them — starting tangled, they never fully untangle.
  if (links.length > 0 && !opts.noWarmStart) {
    const nbs = new Map();
    for (const l of links) {
      if (!nbs.has(l.source)) nbs.set(l.source, []);
      if (!nbs.has(l.target)) nbs.set(l.target, []);
      nbs.get(l.source).push(l.target);
      nbs.get(l.target).push(l.source);
    }
    for (let pass = 0; pass < 40; pass++) {
      for (const [n, list] of nbs) {
        let tx = 0, ty = 0;
        for (const m of list) { tx += m.x; ty += m.y; }
        n.x += (tx / list.length - n.x) * 0.5;
        n.y += (ty / list.length - n.y) * 0.5;
      }
    }
    // deterministic jitter so coincident twins separate cleanly
    nodes.forEach((n, i) => {
      n.x += 3 * Math.cos(i * 2.39996323);
      n.y += 3 * Math.sin(i * 2.39996323);
    });
  }

  function tick() {
    const n = nodes.length;
    // repulsion
    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < n; j++) {
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        if (dx === 0 && dy === 0) dx = 0.01;
        let d2 = dx * dx + dy * dy;
        if (d2 > 250000) continue; // beyond 500px repulsion is negligible
        if (d2 < 100) d2 = 100;    // clamp: overlapping nodes must not explode
        const f = (repulsion * alpha) / d2;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.1;
        const fx = (dx / d) * f;
        const fy = (dy / d) * f;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      }
    }
    // springs
    for (let i = 0; i < links.length; i++) {
      const l = links[i];
      const s = l.source, t = l.target;
      const dx = t.x - s.x, dy = t.y - s.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = springK * springW[i] * (d - restLen) * alpha;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      s.vx += fx; s.vy += fy;
      t.vx -= fx; t.vy -= fy;
    }
    // centering + integrate (speed-capped so nothing gets flung off-map)
    for (const p of nodes) {
      p.vx += (cx - p.x) * centerK * alpha;
      p.vy += (cy - p.y) * centerK * alpha;
      p.vx *= damping;
      p.vy *= damping;
      const sp = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
      if (sp > 24) { p.vx *= 24 / sp; p.vy *= 24 / sp; }
      p.x += p.vx;
      p.y += p.vy;
    }
    // collision: positional separation so circles never overlap.
    // One relaxation per tick converges over the run.
    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      const ra = (a.r || 6) + collidePad / 2;
      for (let j = i + 1; j < n; j++) {
        const b = nodes[j];
        const rb = (b.r || 6) + collidePad / 2;
        const min = ra + rb;
        let dx = b.x - a.x, dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 >= min * min) continue;
        if (d2 === 0) { dx = 0.1; dy = 0.05; d2 = 0.0125; }
        const d = Math.sqrt(d2);
        const push = (min - d) / d / 2;
        const px = dx * push, py = dy * push;
        a.x -= px; a.y -= py;
        b.x += px; b.y += py;
      }
    }
    alpha *= 1 - decay;
    return alpha;
  }

  return {
    tick,
    alpha: () => alpha,
    reheat(a = 0.5) { alpha = Math.max(alpha, a); },
    stop() { alpha = 0; },
  };
}
