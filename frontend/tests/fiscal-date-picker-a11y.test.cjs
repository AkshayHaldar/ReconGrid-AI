const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");

// Compile fiscalDate
const fiscalSource = readFileSync(path.join(__dirname, "../src/lib/fiscalDate.ts"), "utf8");
const fiscalCode = ts.transpileModule(fiscalSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const fiscalExports = {};
vm.runInNewContext(fiscalCode, {
  exports: fiscalExports,
  Date,
  String,
  Number,
  isNaN,
  Math,
  Intl,
  RegExp,
});

function renderPicker(props) {
  let stateMap = new Map();
  let stateIndex = 0;
  const hooks = {
    ...React,
    useState: (initial) => {
      const idx = stateIndex++;
      if (!stateMap.has(idx)) {
        stateMap.set(idx, typeof initial === "function" ? initial() : initial);
      }
      const setter = (val) => {
        stateMap.set(idx, typeof val === "function" ? val(stateMap.get(idx)) : val);
      };
      return [stateMap.get(idx), setter];
    },
    useMemo: (fn) => fn(),
    useCallback: (fn) => fn,
    useEffect: () => {},
    useRef: (val) => ({ current: val }),
  };

  const exports = {};
  const source = readFileSync(
    path.join(__dirname, "../src/components/FiscalDateRangePicker.tsx"),
    "utf8"
  );
  const code = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText;

  vm.runInNewContext(code, {
    exports,
    console: { error() {} },
    require(name) {
      if (name === "react") return hooks;
      if (name === "react/jsx-runtime") return require("react/jsx-runtime");
      if (name === "lucide-react") {
        return new Proxy(
          {},
          {
            get: (_, prop) => (iconProps) => React.createElement("svg", { "data-icon": prop, ...iconProps }),
          }
        );
      }
      if (name === "@/lib/fiscalDate") {
        return fiscalExports;
      }
      return new Proxy({}, { get: () => () => null });
    },
  });

  return exports.FiscalDateRangePicker(props);
}

function collectElements(node, matcher, list = []) {
  if (!node || typeof node !== "object") return list;
  if (matcher(node)) list.push(node);
  const children = React.Children.toArray(node.props?.children);
  for (const child of children) {
    collectElements(child, matcher, list);
  }
  return list;
}

test("unfiltered state renders a single button without nested buttons or role='button'", () => {
  const vdom = renderPicker({
    fromDate: undefined,
    toDate: undefined,
    onChange: () => {},
  });

  const buttons = collectElements(vdom, (el) => el.type === "button");
  assert.equal(buttons.length, 1, "Should have exactly 1 button when unfiltered");

  const nestedInteractive = collectElements(
    buttons[0],
    (el) => el !== buttons[0] && (el.type === "button" || el.props?.role === "button")
  );
  assert.equal(nestedInteractive.length, 0, "No nested buttons or role='button' allowed inside button");
});

test("filtered state renders split button group with two sibling buttons", () => {
  let resetCalled = false;
  const vdom = renderPicker({
    fromDate: "2026-04-01",
    toDate: "2026-06-30",
    onChange: (from, to) => {
      if (from === undefined && to === undefined) resetCalled = true;
    },
  });

  const buttons = collectElements(vdom, (el) => el.type === "button");
  assert.equal(buttons.length, 2, "Should have exactly 2 buttons in split button group when filtered");

  // Neither button should contain another button or role="button"
  for (const btn of buttons) {
    const nested = collectElements(
      btn,
      (el) => el !== btn && (el.type === "button" || el.props?.role === "button")
    );
    assert.equal(nested.length, 0, "Button must not contain nested interactive elements");
  }

  // Find reset button
  const resetBtn = buttons.find((b) => b.props?.["aria-label"] === "Reset Dates");
  assert.ok(resetBtn, "Reset button should have aria-label='Reset Dates'");

  // Simulate click
  resetBtn.props.onClick({ stopPropagation() {} });
  assert.equal(resetCalled, true, "Clicking reset button must invoke onChange(undefined, undefined)");
});
