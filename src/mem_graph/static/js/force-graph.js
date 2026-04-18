(function () {
  /**
   * Helper to resolve link sources and targets to actual node objects.
   */
  function resolveLink(link, map) {
    const source = typeof link.source === 'object' ? link.source : map.get(link.source);
    const target = typeof link.target === 'object' ? link.target : map.get(link.target);
    return (source && target) ? { source, target } : null;
  }

  /**
   * Returns a Map of node ID -> node object.
   */
  function nodeById(nodes) {
    const map = new Map();
    (nodes || []).forEach((node) => map.set(node.id, node));
    return map;
  }

  /**
   * Internal drawing, physics, and animation helpers.
   */
  const GraphUtils = {
    resize(ctx, canvas, container, state, draw) {
      const rect = container.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      state.width = Math.max(320, rect.width || 320);
      state.height = Math.max(320, rect.height || 320);
      canvas.width = Math.floor(state.width * ratio);
      canvas.height = Math.floor(state.height * ratio);
      canvas.style.width = `${state.width}px`;
      canvas.style.height = `${state.height}px`;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw();
    },

    screenToWorld(canvas, state, event) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (event.clientX - rect.left - state.offsetX) / state.scale,
        y: (event.clientY - rect.top - state.offsetY) / state.scale,
      };
    },

    initializePositions(state) {
      const nodes = state.data.nodes || [];
      const radius = Math.max(70, Math.min(state.width, state.height) * 0.32);

      const allNodesHaveCoords = nodes.every((node) => {
        const hasX = typeof node.x === 'number' && !Number.isNaN(node.x);
        const hasY = typeof node.y === 'number' && !Number.isNaN(node.y);
        return hasX && hasY;
      });

      if (!allNodesHaveCoords) {
        nodes.forEach((node, index) => {
          const hasX = typeof node.x === 'number' && !Number.isNaN(node.x);
          const hasY = typeof node.y === 'number' && !Number.isNaN(node.y);
          if (!hasX || !hasY) {
            const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
            node.x = Math.cos(angle) * radius;
            node.y = Math.sin(angle) * radius;
          }
          node.vx = node.vx || 0;
          node.vy = node.vy || 0;
        });
      }

      state.offsetX = state.width / 2;
      state.offsetY = state.height / 2;
      state.scale = 1;
      state.alpha = 0.9;
    },

    tick(state) {
      const nodes = state.data.nodes || [];
      const links = state.data.links || [];
      if (nodes.length === 0) return;
      const map = nodeById(nodes);

      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = (b.x || 0) - (a.x || 0);
          const dy = (b.y || 0) - (a.y || 0);
          const dist2 = Math.max(dx * dx + dy * dy, 80);
          const force = (900 / dist2) * state.alpha;
          const dist = Math.sqrt(dist2);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx -= fx;
          a.vy -= fy;
          b.vx += fx;
          b.vy += fy;
        }
      }

      links.forEach((link) => {
        const resolved = resolveLink(link, map);
        if (!resolved) return;
        const dx = resolved.target.x - resolved.source.x;
        const dy = resolved.target.y - resolved.source.y;
        const distance = Math.max(Math.hypot(dx, dy), 1);
        const desired = 110;
        const force = (distance - desired) * 0.018 * state.alpha;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        resolved.source.vx += fx;
        resolved.source.vy += fy;
        resolved.target.vx -= fx;
        resolved.target.vy -= fy;
      });

      nodes.forEach((node) => {
        if (node === state.draggingNode) return;
        node.vx = (node.vx - node.x * 0.002 * state.alpha) * 0.82;
        node.vy = (node.vy - node.y * 0.002 * state.alpha) * 0.82;
        node.x += node.vx;
        node.y += node.vy;
      });
      state.alpha *= 0.985;
    },

    draw(ctx, state) {
      if (!ctx) return;
      ctx.save();
      ctx.clearRect(0, 0, state.width, state.height);

      if (state.backgroundColor && state.backgroundColor !== 'transparent') {
        ctx.fillStyle = state.backgroundColor;
        ctx.fillRect(0, 0, state.width, state.height);
      }

      ctx.translate(state.offsetX, state.offsetY);
      ctx.scale(state.scale, state.scale);

      const nodes = state.data.nodes || [];
      const map = nodeById(nodes);
      ctx.lineWidth = 1.2 / state.scale;

      (state.data.links || []).forEach((link) => {
        const resolved = resolveLink(link, map);
        if (!resolved) return;
        ctx.beginPath();
        const color = typeof state.linkColor === 'function' ? state.linkColor(link) : state.linkColor;
        ctx.strokeStyle = color;
        ctx.moveTo(resolved.source.x, resolved.source.y);
        ctx.lineTo(resolved.target.x, resolved.target.y);
        ctx.stroke();
      });

      nodes.forEach((node) => {
        const hasX = typeof node.x === 'number' && !Number.isNaN(node.x);
        const hasY = typeof node.y === 'number' && !Number.isNaN(node.y);
        if (!hasX || !hasY) return;

        if (state.nodeCanvasObject) {
          state.nodeCanvasObject(node, ctx, state.scale);
        } else {
          ctx.beginPath();
          ctx.fillStyle = node.color || '#116d72';
          ctx.arc(node.x, node.y, node.val || 8, 0, Math.PI * 2);
          ctx.fill();
        }
      });

      ctx.restore();
    },

    findNode(point, state) {
      const nodes = state.data.nodes || [];
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        const node = nodes[i];
        const radius = (node.val || 12) + 8;
        const dx = point.x - node.x;
        const dy = point.y - node.y;
        if (dx * dx + dy * dy <= radius * radius) return node;
      }
      return null;
    },

    animateTo(state, targets, duration, onTick) {
      const started = performance.now();
      const initial = {};
      Object.keys(targets).forEach((key) => {
        initial[key] = state[key];
      });

      const step = (now) => {
        const t = Math.min(1, (now - started) / duration);
        const ease = t * (2 - t); // Ease out quad
        Object.keys(targets).forEach((key) => {
          state[key] = initial[key] + (targets[key] - initial[key]) * ease;
        });
        onTick();
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    },
  };

  /**
   * Main factory function for the force graph.
   */
  function ForceGraph(container) {
    if (!container) {
      console.error('ForceGraph container is null or undefined');
      return null;
    }

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    container.innerHTML = '';
    container.append(canvas);

    const state = {
      data: { nodes: [], links: [] },
      backgroundColor: 'transparent',
      linkColor: () => 'rgba(0,0,0,0.2)',
      nodeCanvasObject: null,
      nodePointerAreaPaint: null,
      onNodeClick: null,
      width: 0,
      height: 0,
      scale: 1,
      offsetX: 0,
      offsetY: 0,
      draggingNode: null,
      panning: false,
      lastPointer: null,
      hoveredNode: null,
      animation: null,
      alpha: 0.8,
    };

    const draw = () => GraphUtils.draw(ctx, state);
    const resize = () => GraphUtils.resize(ctx, canvas, container, state, draw);

    function animate() {
      GraphUtils.tick(state);
      draw();
      if (state.alpha > 0.02 || state.draggingNode) {
        state.animation = requestAnimationFrame(animate);
      } else {
        state.animation = null;
      }
    }

    function restart() {
      if (!state.animation) {
        state.animation = requestAnimationFrame(animate);
      }
    }

    canvas.addEventListener('pointerdown', (event) => {
      const point = GraphUtils.screenToWorld(canvas, state, event);
      const node = GraphUtils.findNode(point, state);
      state.lastPointer = { x: event.clientX, y: event.clientY };
      if (node) {
        state.draggingNode = node;
        canvas.setPointerCapture(event.pointerId);
      } else {
        state.panning = true;
      }
    });

    canvas.addEventListener('pointermove', (event) => {
      const point = GraphUtils.screenToWorld(canvas, state, event);
      state.hoveredNode = GraphUtils.findNode(point, state);

      let cursor = 'grab';
      if (state.draggingNode) {
        cursor = 'grabbing';
      } else if (state.hoveredNode) {
        cursor = 'pointer';
      } else if (state.panning) {
        cursor = 'grabbing';
      }
      canvas.style.cursor = cursor;

      if (state.draggingNode) {
        state.draggingNode.x = point.x;
        state.draggingNode.y = point.y;
        state.draggingNode.vx = 0;
        state.draggingNode.vy = 0;
        state.alpha = 0.25;
        restart();
      } else if (state.panning && state.lastPointer) {
        state.offsetX += event.clientX - state.lastPointer.x;
        state.offsetY += event.clientY - state.lastPointer.y;
        draw();
      }
      state.lastPointer = { x: event.clientX, y: event.clientY };
    });

    canvas.addEventListener('pointerup', (event) => {
      if (state.draggingNode) {
        canvas.releasePointerCapture(event.pointerId);
      }
      state.draggingNode = null;
      state.panning = false;
    });

    canvas.addEventListener('click', (event) => {
      const node = GraphUtils.findNode(GraphUtils.screenToWorld(canvas, state, event), state);
      if (node && state.onNodeClick) state.onNodeClick(node);
    });

    canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      const before = {
        x: (px - state.offsetX) / state.scale,
        y: (py - state.offsetY) / state.scale,
      };
      const factor = event.deltaY < 0 ? 1.12 : 0.9;
      state.scale = Math.max(0.12, Math.min(8, state.scale * factor));
      state.offsetX = px - before.x * state.scale;
      state.offsetY = py - before.y * state.scale;
      draw();
    }, { passive: false });

    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    const api = {
      getBackgroundColor() {
        return state.backgroundColor;
      },
      setBackgroundColor(value) {
        state.backgroundColor = value;
        draw();
        return api;
      },
      getLinkColor() {
        return state.linkColor;
      },
      setLinkColor(value) {
        state.linkColor = value;
        draw();
        return api;
      },
      linkDirectionalParticles() {
        return api;
      },
      getNodeCanvasObject() {
        return state.nodeCanvasObject;
      },
      setNodeCanvasObject(value) {
        state.nodeCanvasObject = value;
        draw();
        return api;
      },
      getNodePointerAreaPaint() {
        return state.nodePointerAreaPaint;
      },
      setNodePointerAreaPaint(value) {
        state.nodePointerAreaPaint = value;
        return api;
      },
      getOnNodeClick() {
        return state.onNodeClick;
      },
      setOnNodeClick(value) {
        state.onNodeClick = value;
        return api;
      },
      getGraphData() {
        return state.data;
      },
      setGraphData(value) {
        state.data = {
          nodes: (value.nodes || []).map((node) => ({ ...node })),
          links: (value.links || []).map((link) => ({ ...link })),
        };
        GraphUtils.initializePositions(state);
        restart();
        draw();
        return api;
      },
      refresh() {
        resize();
        state.alpha = Math.max(state.alpha, 0.08);
        restart();
        draw();
        return api;
      },
      centerAt(x, y, duration) {
        const targetX = state.width / 2 - x * state.scale;
        const targetY = state.height / 2 - y * state.scale;
        if (duration) {
          GraphUtils.animateTo(state, { offsetX: targetX, offsetY: targetY }, duration, draw);
        } else {
          state.offsetX = targetX;
          state.offsetY = targetY;
          draw();
        }
        return api;
      },
      zoom(value, duration) {
        const target = Math.max(0.12, Math.min(8, value));
        if (duration) {
          GraphUtils.animateTo(state, { scale: target }, duration, draw);
        } else {
          state.scale = target;
          draw();
        }
        return api;
      },
    };

    return api;
  }

  globalThis.ForceGraph = ForceGraph;
})();
