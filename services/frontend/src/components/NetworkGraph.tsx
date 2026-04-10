import { useRef, useEffect, useCallback } from 'react';
import * as d3 from 'd3';
import type { NetworkNode, NetworkEdge } from '../api/client';

interface Props {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  width: number;
  height: number;
  onRouteClick: (routeId: string) => void;
  focusWarehouseId?: string | null;
}

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  type: 'warehouse' | 'route';
  data: NetworkNode;
  parentId?: string;
  anchorX?: number;
  anchorY?: number;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  has_pending_orders: boolean;
}

const WH_W = 76;
const WH_H = 52;
const WH_RX = 10;
const RT_R = 18;
const WH_COL_R = 65;
const RT_COL_R = 36;

const WH_COLOR = '#4c8bf5';

export function extractWarehouseNum(node: NetworkNode): number {
  const label = node.label ?? node.id;
  const m = label.match(/(\d+)/);
  return m ? parseInt(m[1], 10) : Infinity;
}

function rtCargoColor(node: NetworkNode, maxCargo: number): string {
  const cargo = node.latest_y_hat_future ?? 0;
  if (cargo <= 0) return '#6e7681';
  const ratio = cargo / Math.max(maxCargo, 1);
  if (ratio >= 0.66) return '#f85149';
  if (ratio >= 0.33) return '#d29922';
  return '#58a6ff';
}

function layoutForce(
  whAnchors: Map<string, { x: number; y: number }>,
  whStrength: number,
  rtStrength: number,
) {
  let nodes: SimNode[] = [];

  function force(alpha: number) {
    const whPos = new Map<string, { x: number; y: number }>();

    for (const n of nodes) {
      if (n.type === 'warehouse') {
        const anchor = whAnchors.get(n.id);
        if (anchor && n.x != null && n.y != null) {
          n.vx = (n.vx ?? 0) + (anchor.x - n.x) * whStrength * alpha;
          n.vy = (n.vy ?? 0) + (anchor.y - n.y) * whStrength * alpha;
        }
        whPos.set(n.id, { x: n.x ?? 0, y: n.y ?? 0 });
      }
    }

    for (const n of nodes) {
      if (n.type === 'route' && n.parentId) {
        const p = whPos.get(n.parentId);
        if (p && n.x != null && n.y != null) {
          n.vx = (n.vx ?? 0) + (p.x - n.x) * rtStrength * alpha;
          n.vy = (n.vy ?? 0) + (p.y - n.y) * rtStrength * alpha;
        }
      }
    }
  }

  force.initialize = (n: SimNode[]) => {
    nodes = n;
  };
  return force;
}

export default function NetworkGraph({
  nodes,
  edges,
  width,
  height,
  onRouteClick,
  focusWarehouseId,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null);
  const hlRef = useRef<string | null>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const simNodesRef = useRef<SimNode[]>([]);
  const applyHLRef = useRef<(() => void) | null>(null);

  const focusIdRef = useRef(focusWarehouseId);
  const whAnchorsRef = useRef(new Map<string, { x: number; y: number }>());
  const whClusterRRef = useRef(new Map<string, number>());
  const homeTransformRef = useRef(d3.zoomIdentity);
  const justRenderedRef = useRef(false);
  const widthRef = useRef(width);
  const heightRef = useRef(height);

  focusIdRef.current = focusWarehouseId;
  widthRef.current = width;
  heightRef.current = height;

  const render = useCallback(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    hlRef.current = null;

    const warehouses = nodes
      .filter((n) => n.type === 'warehouse')
      .sort((a, b) => extractWarehouseNum(a) - extractWarehouseNum(b));
    const routes = nodes.filter((n) => n.type === 'route');

    const maxCargo = Math.max(
      ...routes.map((r) => r.latest_y_hat_future ?? 0),
      1,
    );

    const whRoutesMap = new Map<string, NetworkNode[]>();
    routes.forEach((r) => {
      const wid = r.office_from_id ?? '';
      if (!whRoutesMap.has(wid)) whRoutesMap.set(wid, []);
      whRoutesMap.get(wid)!.push(r);
    });

    const cx = width / 2;
    const cy = height / 2;

    const SPACE_PER_ROUTE = 10;
    const MIN_CLUSTER_R = 60;
    const whClusterR = new Map<string, number>();
    warehouses.forEach((w) => {
      const rc = whRoutesMap.get(w.id)?.length ?? 0;
      const r = Math.max(MIN_CLUSTER_R, rc * SPACE_PER_ROUTE + RT_COL_R);
      whClusterR.set(w.id, r);
    });

    const padding = 100;
    const whCount = warehouses.length;
    const cols = Math.max(
      1,
      Math.ceil(Math.sqrt(whCount * (width / Math.max(height, 1)))),
    );
    const rows = Math.max(1, Math.ceil(whCount / cols));

    const maxClusterR = Math.max(
      MIN_CLUSTER_R,
      ...Array.from(whClusterR.values()),
    );
    const minCellSize = maxClusterR * 2 + 40;
    const cellW = Math.max(
      minCellSize,
      (width - 2 * padding) / Math.max(cols, 1),
    );
    const cellH = Math.max(
      minCellSize,
      (height - 2 * padding) / Math.max(rows, 1),
    );

    const whAnchors = new Map<string, { x: number; y: number }>();
    warehouses.forEach((w, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      whAnchors.set(w.id, {
        x: padding + cellW * (col + 0.5),
        y: padding + cellH * (row + 0.5),
      });
    });

    whAnchorsRef.current = whAnchors;
    whClusterRRef.current = whClusterR;

    /* ── simulation nodes ── */
    const simNodes: SimNode[] = [];

    warehouses.forEach((w) => {
      const anchor = whAnchors.get(w.id) ?? { x: cx, y: cy };
      simNodes.push({
        id: w.id,
        type: 'warehouse',
        data: w,
        x: anchor.x,
        y: anchor.y,
        anchorX: anchor.x,
        anchorY: anchor.y,
      });
    });

    routes.forEach((r) => {
      const pid = r.office_from_id ?? '';
      const parentAnchor = whAnchors.get(pid);
      const siblings = whRoutesMap.get(pid) ?? [];
      const si = siblings.indexOf(r);
      const angle = (2 * Math.PI * si) / Math.max(siblings.length, 1);
      const orbitR = whClusterR.get(pid) ?? MIN_CLUSTER_R;
      simNodes.push({
        id: r.id,
        type: 'route',
        data: r,
        parentId: r.office_from_id,
        x: (parentAnchor?.x ?? cx) + orbitR * Math.cos(angle),
        y: (parentAnchor?.y ?? cy) + orbitR * Math.sin(angle),
      });
    });

    simNodesRef.current = simNodes;

    /* ── links: warehouse → route (backend sends route→wh, we swap) ── */
    const nodeIdSet = new Set(simNodes.map((n) => n.id));
    const typeMap = new Map(simNodes.map((n) => [n.id, n.type]));
    const simLinks: SimLink[] = edges
      .map((e) => ({
        source: e.target,
        target: e.source,
        has_pending_orders: e.has_pending_orders,
      }))
      .filter(
        (l) =>
          nodeIdSet.has(l.source as string) &&
          nodeIdSet.has(l.target as string) &&
          typeMap.get(l.source as string) === 'warehouse' &&
          typeMap.get(l.target as string) === 'route',
      );

    /* ── force simulation ── */
    const sim = d3
      .forceSimulation<SimNode>(simNodes)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance((d) => {
            const src = d.source as SimNode;
            return whClusterR.get(src.id) ?? 100;
          })
          .strength(0.8),
      )
      .force(
        'charge',
        d3
          .forceManyBody<SimNode>()
          .strength((d) => (d.type === 'warehouse' ? -600 : -60)),
      )
      .force(
        'collision',
        d3
          .forceCollide<SimNode>()
          .radius((d) => (d.type === 'warehouse' ? WH_COL_R : RT_COL_R))
          .strength(1)
          .iterations(3),
      )
      .force('layout', layoutForce(whAnchors, 0.5, 0.3))
      .alphaDecay(0.02)
      .velocityDecay(0.4);

    simRef.current = sim;

    /* ── SVG defs ── */
    const defs = svg.append('defs');

    const glow = defs.append('filter').attr('id', 'glow');
    glow
      .append('feGaussianBlur')
      .attr('stdDeviation', '2')
      .attr('result', 'b');
    const fm = glow.append('feMerge');
    fm.append('feMergeNode').attr('in', 'b');
    fm.append('feMergeNode').attr('in', 'SourceGraphic');

    function mkArrow(id: string, fill: string) {
      defs
        .append('marker')
        .attr('id', id)
        .attr('viewBox', '0 -4 8 8')
        .attr('refX', 8)
        .attr('refY', 0)
        .attr('markerWidth', 8)
        .attr('markerHeight', 8)
        .attr('markerUnits', 'userSpaceOnUse')
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-3L8,0L0,3')
        .attr('fill', fill);
    }
    mkArrow('arr', '#30363d');
    mkArrow('arr-p', '#d29922');

    /* ── zoom ── */
    const g = svg.append('g');

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 5])
      .on('zoom', (ev) => g.attr('transform', ev.transform));

    svg.call(zoom);
    zoomRef.current = zoom;

    /* ── compute default home transform (first few warehouses) ── */
    let homeTransform = d3.zoomIdentity;
    const initCount = Math.min(4, warehouses.length);
    if (initCount > 0) {
      const initAnchors = warehouses
        .slice(0, initCount)
        .map((w) => whAnchors.get(w.id))
        .filter(Boolean) as { x: number; y: number }[];

      if (initAnchors.length > 0) {
        const viewPad = maxClusterR + 60;
        const minX = Math.min(...initAnchors.map((a) => a.x)) - viewPad;
        const maxXv = Math.max(...initAnchors.map((a) => a.x)) + viewPad;
        const minY = Math.min(...initAnchors.map((a) => a.y)) - viewPad;
        const maxYv = Math.max(...initAnchors.map((a) => a.y)) + viewPad;

        const bw = maxXv - minX;
        const bh = maxYv - minY;
        const scale = Math.min(width / bw, height / bh) * 0.85;
        const midX = (minX + maxXv) / 2;
        const midY = (minY + maxYv) / 2;

        homeTransform = d3.zoomIdentity
          .translate(width / 2 - midX * scale, height / 2 - midY * scale)
          .scale(scale);
      }
    }
    homeTransformRef.current = homeTransform;

    /* ── apply initial camera (read current focus from ref) ── */
    const currentFocus = focusIdRef.current;
    if (currentFocus) {
      const focusAnchor = whAnchors.get(currentFocus);
      if (focusAnchor) {
        const clR = whClusterR.get(currentFocus) ?? MIN_CLUSTER_R;
        const viewPad = clR + 80;
        const sc = Math.min(
          width / (2 * viewPad),
          height / (2 * viewPad),
          2.2,
        );
        svg.call(
          zoom.transform,
          d3.zoomIdentity
            .translate(width / 2 - focusAnchor.x * sc, height / 2 - focusAnchor.y * sc)
            .scale(sc),
        );
      } else {
        svg.call(zoom.transform, homeTransform);
      }
      hlRef.current = currentFocus;
    } else {
      svg.call(zoom.transform, homeTransform);
    }

    svg.on('dblclick.zoom', () =>
      svg
        .transition()
        .duration(400)
        .call(zoom.transform, homeTransformRef.current),
    );

    /* ── cluster backgrounds ── */
    const clusterBg = g.append('g').attr('class', 'cluster-bg');

    function updateClusterBgs() {
      const clusters: Map<string, { xs: number[]; ys: number[] }> =
        new Map();
      for (const n of simNodes) {
        const wid = n.type === 'warehouse' ? n.id : n.parentId;
        if (!wid) continue;
        if (!clusters.has(wid))
          clusters.set(wid, { xs: [], ys: [] });
        const c = clusters.get(wid)!;
        c.xs.push(n.x ?? 0);
        c.ys.push(n.y ?? 0);
      }

      const bgData = Array.from(clusters.entries()).map(
        ([wid, { xs, ys }]) => {
          const mx =
            xs.reduce((a, b) => a + b, 0) / xs.length;
          const my =
            ys.reduce((a, b) => a + b, 0) / ys.length;
          const maxDist = Math.max(
            40,
            ...xs.map((x, i) =>
              Math.sqrt((x - mx) ** 2 + (ys[i] - my) ** 2),
            ),
          );
          return { wid, cx: mx, cy: my, r: maxDist + 30 };
        },
      );

      clusterBg
        .selectAll<SVGCircleElement, (typeof bgData)[0]>('circle')
        .data(bgData, (d) => d.wid)
        .join('circle')
        .attr('cx', (d) => d.cx)
        .attr('cy', (d) => d.cy)
        .attr('r', (d) => d.r)
        .attr('fill', 'rgba(76,139,245,0.04)')
        .attr('stroke', 'rgba(76,139,245,0.08)')
        .attr('stroke-width', 1)
        .attr('stroke-dasharray', '4,4');
    }

    /* ── draw links ── */
    const linkSel = g
      .append('g')
      .selectAll<SVGLineElement, SimLink>('line')
      .data(simLinks)
      .join('line')
      .attr('stroke', (d) =>
        d.has_pending_orders ? '#d29922' : '#30363d',
      )
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', (d) =>
        d.has_pending_orders ? '6,3' : 'none',
      )
      .attr('stroke-opacity', 0.55)
      .attr('marker-end', (d) =>
        d.has_pending_orders ? 'url(#arr-p)' : 'url(#arr)',
      );

    /* ── draw nodes ── */
    const nodeSel = g
      .append('g')
      .selectAll<SVGGElement, SimNode>('g')
      .data(simNodes)
      .join('g')
      .attr('class', 'node')
      .style('cursor', 'pointer');

    /* warehouse shapes — single color */
    const wSel = nodeSel.filter((d) => d.type === 'warehouse');

    wSel
      .append('rect')
      .attr('x', -WH_W / 2)
      .attr('y', -WH_H / 2)
      .attr('width', WH_W)
      .attr('height', WH_H)
      .attr('rx', WH_RX)
      .attr('fill', WH_COLOR)
      .attr('stroke', '#0d1117')
      .attr('stroke-width', 2)
      .attr('filter', 'url(#glow)');

    wSel
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', -4)
      .attr('fill', '#fff')
      .attr('font-size', 11)
      .attr('font-weight', 700)
      .text((d) => {
        const l = d.data.label ?? d.id;
        return l.replace(/^Warehouse\s*/i, 'WH ');
      });

    wSel
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', 14)
      .attr('fill', 'rgba(255,255,255,0.7)')
      .attr('font-size', 9)
      .text((d) => {
        const f =
          (d.data.free_gazel ?? 0) + (d.data.free_fura ?? 0);
        const b =
          (d.data.busy_gazel ?? 0) + (d.data.busy_fura ?? 0);
        return `${f} free / ${b} busy`;
      });

    /* route shapes — colored by cargo volume */
    const rSel = nodeSel.filter((d) => d.type === 'route');

    rSel
      .append('circle')
      .attr('r', RT_R)
      .attr('fill', (d) => rtCargoColor(d.data, maxCargo))
      .attr('stroke', '#0d1117')
      .attr('stroke-width', 1.5);

    rSel
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', 4)
      .attr('fill', '#fff')
      .attr('font-size', 8)
      .attr('font-weight', 600)
      .text((d) =>
        d.id.length > 8 ? '\u2026' + d.id.slice(-6) : d.id,
      );

    /* route info labels */
    rSel.each(function (d) {
      const group = d3.select(this);
      const totalVeh = d.data.trucks
        ? d.data.trucks.reduce((sum, t) => sum + t.count, 0)
        : 0;
      const orders = d.data.active_orders ?? 0;
      const duration = d.data.avg_duration_min;

      group
        .append('text')
        .attr('text-anchor', 'middle')
        .attr('y', RT_R + 13)
        .attr('fill', 'rgba(255,255,255,0.55)')
        .attr('font-size', 7.5)
        .text(`${orders} ord \u00b7 ${totalVeh} veh`);

      if (duration) {
        group
          .append('text')
          .attr('text-anchor', 'middle')
          .attr('y', RT_R + 23)
          .attr('fill', 'rgba(255,255,255,0.4)')
          .attr('font-size', 7)
          .text(`\u223c${Math.round(duration)} min`);
      }
    });

    /* ── tooltip ── */
    const tip = d3
      .select('body')
      .append('div')
      .attr('class', 'graph-tooltip')
      .style('position', 'absolute')
      .style('pointer-events', 'none')
      .style('background', 'rgba(28,33,40,0.97)')
      .style('border', '1px solid #30363d')
      .style('border-radius', '10px')
      .style('padding', '12px 16px')
      .style('font-size', '12px')
      .style('font-family', 'system-ui, sans-serif')
      .style('color', '#e1e4e8')
      .style('display', 'none')
      .style('z-index', '9999')
      .style('line-height', '1.6')
      .style('box-shadow', '0 8px 24px rgba(0,0,0,0.5)')
      .style('max-width', '320px');

    nodeSel
      .on('mouseenter', (ev, d) => {
        let html = '';
        if (d.type === 'warehouse') {
          const rc = whRoutesMap.get(d.id)?.length ?? 0;
          html =
            `<div style="font-weight:700;font-size:14px;margin-bottom:6px">${d.data.label ?? d.id}</div>` +
            `<div style="color:#8b949e;margin-bottom:4px">Routes: ${rc}</div>` +
            `<div>Gazel: <span style="color:#3fb950">${d.data.free_gazel ?? 0} free</span>` +
            ` / <span style="color:#f85149">${d.data.busy_gazel ?? 0} busy</span></div>` +
            `<div>Fura: <span style="color:#3fb950">${d.data.free_fura ?? 0} free</span>` +
            ` / <span style="color:#f85149">${d.data.busy_fura ?? 0} busy</span></div>`;
        } else {
          const trucks = d.data.trucks;
          const totalVeh = trucks
            ? trucks.reduce((s, t) => s + t.count, 0)
            : 0;
          const truckHtml =
            trucks && trucks.length > 0
              ? trucks
                  .map(
                    (t) =>
                      `<div style="display:flex;justify-content:space-between"><span>${t.type}</span><b>${t.count}</b></div>`,
                  )
                  .join('')
              : '<div style="color:#6e7681">No active vehicles</div>';

          html =
            `<div style="font-weight:700;font-size:14px;margin-bottom:6px">Route ${d.id}</div>` +
            `<div style="color:#8b949e;margin-bottom:4px">Warehouse: ${d.parentId ?? '\u2014'}</div>` +
            `<div style="display:grid;grid-template-columns:1fr auto;gap:2px 12px;margin-bottom:8px">` +
            `<span style="color:#8b949e">Cargo forecast</span><b>${(d.data.latest_y_hat_future ?? 0).toFixed(1)} units</b>` +
            `<span style="color:#8b949e">Active orders</span><b>${d.data.active_orders ?? 0}</b>` +
            `<span style="color:#8b949e">Vehicles on route</span><b>${totalVeh}</b>` +
            (d.data.avg_duration_min
              ? `<span style="color:#8b949e">Avg trip duration</span><b>\u223c${Math.round(d.data.avg_duration_min)} min</b>`
              : '') +
            `<span style="color:#8b949e">Horizon</span><b>h${d.data.latest_horizon ?? '\u2014'}</b>` +
            `<span style="color:#8b949e">Confidence</span><b>${((d.data.latest_confidence ?? 0) * 100).toFixed(0)}%</b>` +
            `</div>` +
            `<div style="border-top:1px solid #21262d;padding-top:6px;font-weight:600;margin-bottom:4px">Vehicles</div>` +
            truckHtml +
            `<div style="color:#6e7681;font-size:10px;margin-top:6px">Click for details</div>`;
        }
        tip
          .style('display', 'block')
          .html(html)
          .style('left', `${ev.pageX + 14}px`)
          .style('top', `${ev.pageY - 14}px`);
      })
      .on('mousemove', (ev) => {
        tip
          .style('left', `${ev.pageX + 14}px`)
          .style('top', `${ev.pageY - 14}px`);
      })
      .on('mouseleave', () => {
        tip.style('display', 'none');
      });

    /* ── highlight on warehouse click ── */
    function applyHL() {
      const wid = hlRef.current;
      if (wid) {
        nodeSel
          .transition()
          .duration(200)
          .attr('opacity', (d) => {
            if (d.type === 'warehouse' && d.id === wid) return 1;
            if (d.type === 'route' && d.parentId === wid) return 1;
            return 0.1;
          });
        linkSel
          .transition()
          .duration(200)
          .attr('stroke-opacity', (d) => {
            const src = d.source as SimNode;
            return src.type === 'warehouse' && src.id === wid
              ? 0.7
              : 0.03;
          });
      } else {
        nodeSel
          .transition()
          .duration(200)
          .attr('opacity', 1);
        linkSel
          .transition()
          .duration(200)
          .attr('stroke-opacity', 0.55);
      }
    }

    applyHLRef.current = applyHL;
    if (currentFocus) applyHL();

    nodeSel.on('click', (ev, d) => {
      ev.stopPropagation();
      if (d.type === 'route') {
        onRouteClick(d.id);
      } else {
        hlRef.current =
          hlRef.current === d.id ? null : d.id;
        applyHL();
      }
    });

    svg.on('click.hl', () => {
      hlRef.current = null;
      applyHL();
    });

    /* ── pre-compute layout (no async jitter) ── */
    sim.stop();
    for (let i = 0; i < 300; i++) sim.tick();

    function updatePositions() {
      linkSel.each(function (d) {
        const s = d.source as SimNode;
        const t = d.target as SimNode;
        const sx = s.x ?? 0;
        const sy = s.y ?? 0;
        const tx = t.x ?? 0;
        const ty = t.y ?? 0;
        const dx = tx - sx;
        const dy = ty - sy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const srcPad =
          s.type === 'warehouse' ? WH_COL_R - 4 : RT_R + 2;
        const tgtPad =
          t.type === 'route' ? RT_R + 10 : WH_COL_R + 4;

        d3.select(this)
          .attr('x1', sx + (dx * srcPad) / dist)
          .attr('y1', sy + (dy * srcPad) / dist)
          .attr('x2', tx - (dx * tgtPad) / dist)
          .attr('y2', ty - (dy * tgtPad) / dist);
      });

      nodeSel.attr(
        'transform',
        (d) => `translate(${d.x ?? 0},${d.y ?? 0})`,
      );

      updateClusterBgs();
    }
    updatePositions();

    /* ── drag (no simulation restart) ── */
    const drag = d3
      .drag<SVGGElement, SimNode>()
      .on('start', (_ev, d) => {
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (ev, d) => {
        d.x = ev.x;
        d.y = ev.y;
        d.fx = ev.x;
        d.fy = ev.y;
        updatePositions();
      })
      .on('end', (_ev, d) => {
        d.fx = null;
        d.fy = null;
      });

    nodeSel.call(drag);

    justRenderedRef.current = true;

    return () => {
      tip.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, width, height, onRouteClick]);

  useEffect(() => {
    hlRef.current = null;
    const cleanup = render();
    return () => {
      simRef.current?.stop();
      d3.selectAll('.graph-tooltip').remove();
      cleanup?.();
    };
  }, [render]);

  /* ── smooth focus transitions (no full re-render) ── */
  useEffect(() => {
    if (justRenderedRef.current) {
      justRenderedRef.current = false;
      return;
    }
    if (!zoomRef.current || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    const w = widthRef.current;
    const h = heightRef.current;

    if (focusWarehouseId) {
      const anchor = whAnchorsRef.current.get(focusWarehouseId);
      if (!anchor) return;
      const clR = whClusterRRef.current.get(focusWarehouseId) ?? 60;
      const viewPad = clR + 80;
      const sc = Math.min(w / (2 * viewPad), h / (2 * viewPad), 2.2);
      const tx = w / 2 - anchor.x * sc;
      const ty = h / 2 - anchor.y * sc;

      svg
        .transition()
        .duration(400)
        .call(
          zoomRef.current.transform,
          d3.zoomIdentity.translate(tx, ty).scale(sc),
        );

      hlRef.current = focusWarehouseId;
      applyHLRef.current?.();
    } else {
      svg
        .transition()
        .duration(400)
        .call(zoomRef.current.transform, homeTransformRef.current);
      hlRef.current = null;
      applyHLRef.current?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusWarehouseId]);

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      style={{
        background: '#0d1117',
        borderRadius: 12,
        border: '1px solid #21262d',
      }}
    />
  );
}
