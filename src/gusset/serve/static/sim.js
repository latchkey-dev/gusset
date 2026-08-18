// A small dependency-free force simulation for the symbol graph.
// Deliberate: zero external deps means the page works offline forever.
// Forces: pairwise repulsion, spring along edges, weak centering;
// velocity damping; alpha decay. O(n²) repulsion is fine at ~600 nodes.

export function createSim(nodes, links, opts = {}) {
  const width = opts.width ?? 800;
  const height = opts.height ?? 600;
  const repulsion = opts.repulsion ?? 1600;
  const springK = opts.springK ?? 0.05;
  const restLen = opts.restLen ?? 52;
  const centerK = opts.centerK ?? 0.012;
  const damping = opts.damping ?? 0.6;
  const decay = opts.decay ?? 0.024;

  let alpha = 1;
  const cx = width / 2;
  const cy = height / 2;

  // Deterministic phyllotaxis start so reloads look the same.
  nodes.forEach((n, i) => {
    if (n.x == null || n.y == null) {
      const a = i * 2.39996323;
      const r = 14 * Math.sqrt(i + 1);
      n.x = cx + r * Math.cos(a);
      n.y = cy + r * Math.sin(a);
    }
    n.vx = 0;
    n.vy = 0;
  });

  function tick() {
    const n = nodes.length;
    // repulsion
    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < n; j++) {
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = b.y === a.y && dx === 0 ? 0.01 : a.y - b.y;
        if (dx === 0 && dy === 0) dx = 0.01;
        const d2 = dx * dx + dy * dy;
        if (d2 > 90000) continue; // beyond 300px repulsion is negligible
        const f = (repulsion * alpha) / d2;
        const d = Math.sqrt(d2);
        const fx = (dx / d) * f;
        const fy = (dy / d) * f;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      }
    }
    // springs
    for (const l of links) {
      const s = l.source, t = l.target;
      const dx = t.x - s.x, dy = t.y - s.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = springK * (d - restLen) * alpha;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      s.vx += fx; s.vy += fy;
      t.vx -= fx; t.vy -= fy;
    }
    // centering + integrate
    for (const p of nodes) {
      p.vx += (cx - p.x) * centerK * alpha;
      p.vy += (cy - p.y) * centerK * alpha;
      p.vx *= damping;
      p.vy *= damping;
      p.x += p.vx;
      p.y += p.vy;
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
