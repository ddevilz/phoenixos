import "@testing-library/jest-dom/vitest";

// react-force-graph-2d renders to canvas; stub getContext so jsdom doesn't throw.
HTMLCanvasElement.prototype.getContext = (() => null) as never;
