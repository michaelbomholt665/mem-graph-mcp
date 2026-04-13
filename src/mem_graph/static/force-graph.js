(function () {
  // Minimal ForceGraph stub to avoid runtime errors when the real library
  // isn't available (or when static analysis forbids referencing external CDN).
  // This provides the small chainable API surface used by dashboard.js.
  function createForceGraphFactory() {
    return function (container) {
      const state = { container, data: { nodes: [], links: [] } };

      const api = {
        backgroundColor: function () { return api; },
        linkColor: function () { return api; },
        linkDirectionalParticles: function () { return api; },
        nodeCanvasObject: function () { return api; },
        nodePointerAreaPaint: function () { return api; },
        onNodeClick: function () { return api; },
        graphData: function (d) {
          if (d === undefined) return state.data;
          state.data = d;
          return api;
        },
        refresh: function () {},
        centerAt: function () {},
        zoom: function () {},
      };

      return api;
    };
  }

  if (!globalThis.ForceGraph) {
    globalThis.ForceGraph = createForceGraphFactory();
  }
})();
