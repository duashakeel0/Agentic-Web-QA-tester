import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement scrollIntoView at all - components that call it
// (chat panels, anything that auto-scrolls to the latest message) would
// otherwise throw in every test that renders them, regardless of whether
// the test cares about scrolling.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
