(function () {
  function createForceGraphFactory() {
    return function createGraph(container) {
      if (!container) {
        console.error("ForceGraph container is null or undefined");
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

      function resize() {
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
      }

      function screenToWorld(event) {
        const rect = canvas.getBoundingClientRect();
        return {
          x: (event.clientX - rect.left - state.offsetX) / state.scale,
          y: (event.clientY - rect.top - state.offsetY) / state.scale,
        };
      }

      function initializePositions() {
        const nodes = state.data.nodes || [];
        const radius = Math.max(70, Math.min(state.width, state.height) * 0.32);
        nodes.forEach((node, index) => {
          if (typeof node.x !== 'number' || typeof node.y !== 'number') {
            const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
            node.x = Math.cos(angle) * radius;
            node.y = Math.sin(angle) * radius;
          }
          node.vx = node.vx || 0;
          node.vy = node.vy || 0;
        });
        state.offsetX = state.width / 2;
        state.offsetY = state.height / 2;
        state.scale = 1;
        state.alpha = 0.9;
      }

      function nodeById() {
        const map = new Map();
        (state.data.nodes || []).forEach((node) => map.set(node.id, node));
        return map;
      }

      function resolveLink(link, map) {
        const source = typeof link.source === 'object' ? link.source : map.get(link.source);
        const target = typeof link.target === 'object' ? link.target : map.get(link.target);
        return source && target ? { source, target } : null;
      }

      function tick() {
        const nodes = state.data.nodes || [];
        const links = state.data.links || [];
        if (!nodes.length) return;
        const map = nodeById();

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
          const distance = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
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
      }

      function draw() {
        if (!ctx) return;
        ctx.save();
        ctx.clearRect(0, 0, state.width, state.height);
        if (state.backgroundColor && state.backgroundColor !== 'transparent') {
          ctx.fillStyle = state.backgroundColor;
          ctx.fillRect(0, 0, state.width, state.height);
        }
        ctx.translate(state.offsetX, state.offsetY);
        ctx.scale(state.scale, state.scale);

        const map = nodeById();
        ctx.lineWidth = 1.2 / state.scale;
        (state.data.links || []).forEach((link) => {
          const resolved = resolveLink(link, map);
          if (!resolved) return;
          ctx.beginPath();
          ctx.strokeStyle = typeof state.linkColor === 'function' ? state.linkColor(link) : state.linkColor;
          ctx.moveTo(resolved.source.x, resolved.source.y);
          ctx.lineTo(resolved.target.x, resolved.target.y);
          ctx.stroke();
        });

        (state.data.nodes || []).forEach((node) => {
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
      }

      function animate() {
        tick();
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

      function findNode(point) {
        const nodes = state.data.nodes || [];
        for (let i = nodes.length - 1; i >= 0; i -= 1) {
          const node = nodes[i];
          const radius = (node.val || 12) + 8;
          const dx = point.x - node.x;
          const dy = point.y - node.y;
          if (dx * dx + dy * dy <= radius * radius) return node;
        }
        return null;
      }

      canvas.addEventListener('pointerdown', (event) => {
        const point = screenToWorld(event);
        const node = findNode(point);
        state.lastPointer = { x: event.clientX, y: event.clientY };
        if (node) {
          state.draggingNode = node;
          canvas.setPointerCapture(event.pointerId);
        } else {
          state.panning = true;
        }
      });

      canvas.addEventListener('pointermove', (event) => {
        const point = screenToWorld(event);
        state.hoveredNode = findNode(point);
        canvas.style.cursor = state.draggingNode ? 'grabbing' : state.hoveredNode ? 'pointer' : state.panning ? 'grabbing' : 'grab';
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
        const node = findNode(screenToWorld(event));
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
        backgroundColor(value) {
          if (value === undefined) return state.backgroundColor;
          state.backgroundColor = value;
          draw();
          return api;
        },
        linkColor(value) {
          if (value === undefined) return state.linkColor;
          state.linkColor = value;
          draw();
          return api;
        },
        linkDirectionalParticles() {
          return api;
        },
        nodeCanvasObject(value) {
          if (value === undefined) return state.nodeCanvasObject;
          state.nodeCanvasObject = value;
          draw();
          return api;
        },
        nodePointerAreaPaint(value) {
          if (value === undefined) return state.nodePointerAreaPaint;
          state.nodePointerAreaPaint = value;
          return api;
        },
        onNodeClick(value) {
          if (value === undefined) return state.onNodeClick;
          state.onNodeClick = value;
          return api;
        },
        graphData(value) {
          if (value === undefined) return state.data;
          state.data = {
            nodes: (value.nodes || []).map((node) => ({ ...node })),
            links: (value.links || []).map((link) => ({ ...link })),
          };
          initializePositions();
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
          if (!duration) {
            state.offsetX = targetX;
            state.offsetY = targetY;
            draw();
            return api;
          }
          const startX = state.offsetX;
          const startY = state.offsetY;
          const started = performance.now();
          function step(now) {
            const t = Math.min(1, (now - started) / duration);
            state.offsetX = startX + (targetX - startX) * t;
            state.offsetY = startY + (targetY - startY) * t;
            draw();
            if (t < 1) requestAnimationFrame(step);
          }
          requestAnimationFrame(step);
          return api;
        },
        zoom(value, duration) {
          const target = Math.max(0.12, Math.min(8, value));
          if (!duration) {
            state.scale = target;
            draw();
            return api;
          }
          const start = state.scale;
          const started = performance.now();
          function step(now) {
            const t = Math.min(1, (now - started) / duration);
            state.scale = start + (target - start) * t;
            draw();
            if (t < 1) requestAnimationFrame(step);
          }
          requestAnimationFrame(step);
          return api;
        },
      };

      return api;
    };
  }

  globalThis.ForceGraph = createForceGraphFactory();
})();
