const {
  SvelteComponent: X,
  assign: Y,
  create_slot: Z,
  detach: p,
  element: x,
  get_all_dirty_from_scope: $,
  get_slot_changes: ee,
  get_spread_update: te,
  init: le,
  insert: ne,
  safe_not_equal: fe,
  set_dynamic_element_data: D,
  set_style: r,
  toggle_class: g,
  transition_in: H,
  transition_out: J,
  update_slot_base: ie
} = window.__gradio__svelte__internal;
function ae(n) {
  let e, t, l;
  const f = (
    /*#slots*/
    n[17].default
  ), a = Z(
    f,
    n,
    /*$$scope*/
    n[16],
    null
  );
  let o = [
    { "data-testid": (
      /*test_id*/
      n[7]
    ) },
    { id: (
      /*elem_id*/
      n[2]
    ) },
    {
      class: t = "block " + /*elem_classes*/
      n[3].join(" ") + " svelte-1t38q2d"
    }
  ], _ = {};
  for (let i = 0; i < o.length; i += 1)
    _ = Y(_, o[i]);
  return {
    c() {
      e = x(
        /*tag*/
        n[14]
      ), a && a.c(), D(
        /*tag*/
        n[14]
      )(e, _), g(
        e,
        "hidden",
        /*visible*/
        n[10] === !1
      ), g(
        e,
        "padded",
        /*padding*/
        n[6]
      ), g(
        e,
        "border_focus",
        /*border_mode*/
        n[5] === "focus"
      ), g(e, "hide-container", !/*explicit_call*/
      n[8] && !/*container*/
      n[9]), r(e, "height", typeof /*height*/
      n[0] == "number" ? (
        /*height*/
        n[0] + "px"
      ) : void 0), r(e, "width", typeof /*width*/
      n[1] == "number" ? `calc(min(${/*width*/
      n[1]}px, 100%))` : void 0), r(
        e,
        "border-style",
        /*variant*/
        n[4]
      ), r(
        e,
        "overflow",
        /*allow_overflow*/
        n[11] ? "visible" : "hidden"
      ), r(
        e,
        "flex-grow",
        /*scale*/
        n[12]
      ), r(e, "min-width", `calc(min(${/*min_width*/
      n[13]}px, 100%))`), r(e, "border-width", "var(--block-border-width)");
    },
    m(i, s) {
      ne(i, e, s), a && a.m(e, null), l = !0;
    },
    p(i, s) {
      a && a.p && (!l || s & /*$$scope*/
      65536) && ie(
        a,
        f,
        i,
        /*$$scope*/
        i[16],
        l ? ee(
          f,
          /*$$scope*/
          i[16],
          s,
          null
        ) : $(
          /*$$scope*/
          i[16]
        ),
        null
      ), D(
        /*tag*/
        i[14]
      )(e, _ = te(o, [
        (!l || s & /*test_id*/
        128) && { "data-testid": (
          /*test_id*/
          i[7]
        ) },
        (!l || s & /*elem_id*/
        4) && { id: (
          /*elem_id*/
          i[2]
        ) },
        (!l || s & /*elem_classes*/
        8 && t !== (t = "block " + /*elem_classes*/
        i[3].join(" ") + " svelte-1t38q2d")) && { class: t }
      ])), g(
        e,
        "hidden",
        /*visible*/
        i[10] === !1
      ), g(
        e,
        "padded",
        /*padding*/
        i[6]
      ), g(
        e,
        "border_focus",
        /*border_mode*/
        i[5] === "focus"
      ), g(e, "hide-container", !/*explicit_call*/
      i[8] && !/*container*/
      i[9]), s & /*height*/
      1 && r(e, "height", typeof /*height*/
      i[0] == "number" ? (
        /*height*/
        i[0] + "px"
      ) : void 0), s & /*width*/
      2 && r(e, "width", typeof /*width*/
      i[1] == "number" ? `calc(min(${/*width*/
      i[1]}px, 100%))` : void 0), s & /*variant*/
      16 && r(
        e,
        "border-style",
        /*variant*/
        i[4]
      ), s & /*allow_overflow*/
      2048 && r(
        e,
        "overflow",
        /*allow_overflow*/
        i[11] ? "visible" : "hidden"
      ), s & /*scale*/
      4096 && r(
        e,
        "flex-grow",
        /*scale*/
        i[12]
      ), s & /*min_width*/
      8192 && r(e, "min-width", `calc(min(${/*min_width*/
      i[13]}px, 100%))`);
    },
    i(i) {
      l || (H(a, i), l = !0);
    },
    o(i) {
      J(a, i), l = !1;
    },
    d(i) {
      i && p(e), a && a.d(i);
    }
  };
}
function se(n) {
  let e, t = (
    /*tag*/
    n[14] && ae(n)
  );
  return {
    c() {
      t && t.c();
    },
    m(l, f) {
      t && t.m(l, f), e = !0;
    },
    p(l, [f]) {
      /*tag*/
      l[14] && t.p(l, f);
    },
    i(l) {
      e || (H(t, l), e = !0);
    },
    o(l) {
      J(t, l), e = !1;
    },
    d(l) {
      t && t.d(l);
    }
  };
}
function _e(n, e, t) {
  let { $$slots: l = {}, $$scope: f } = e, { height: a = void 0 } = e, { width: o = void 0 } = e, { elem_id: _ = "" } = e, { elem_classes: i = [] } = e, { variant: s = "solid" } = e, { border_mode: u = "base" } = e, { padding: m = !0 } = e, { type: h = "normal" } = e, { test_id: y = void 0 } = e, { explicit_call: k = !1 } = e, { container: b = !0 } = e, { visible: w = !0 } = e, { allow_overflow: S = !0 } = e, { scale: C = null } = e, { min_width: B = 0 } = e, d = h === "fieldset" ? "fieldset" : "div";
  return n.$$set = (c) => {
    "height" in c && t(0, a = c.height), "width" in c && t(1, o = c.width), "elem_id" in c && t(2, _ = c.elem_id), "elem_classes" in c && t(3, i = c.elem_classes), "variant" in c && t(4, s = c.variant), "border_mode" in c && t(5, u = c.border_mode), "padding" in c && t(6, m = c.padding), "type" in c && t(15, h = c.type), "test_id" in c && t(7, y = c.test_id), "explicit_call" in c && t(8, k = c.explicit_call), "container" in c && t(9, b = c.container), "visible" in c && t(10, w = c.visible), "allow_overflow" in c && t(11, S = c.allow_overflow), "scale" in c && t(12, C = c.scale), "min_width" in c && t(13, B = c.min_width), "$$scope" in c && t(16, f = c.$$scope);
  }, [
    a,
    o,
    _,
    i,
    s,
    u,
    m,
    y,
    k,
    b,
    w,
    S,
    C,
    B,
    d,
    h,
    f,
    l
  ];
}
class oe extends X {
  constructor(e) {
    super(), le(this, e, _e, se, fe, {
      height: 0,
      width: 1,
      elem_id: 2,
      elem_classes: 3,
      variant: 4,
      border_mode: 5,
      padding: 6,
      type: 15,
      test_id: 7,
      explicit_call: 8,
      container: 9,
      visible: 10,
      allow_overflow: 11,
      scale: 12,
      min_width: 13
    });
  }
}
const {
  SvelteComponent: ce,
  attr: de,
  create_slot: ue,
  detach: re,
  element: me,
  get_all_dirty_from_scope: be,
  get_slot_changes: ge,
  init: he,
  insert: we,
  safe_not_equal: ve,
  transition_in: ye,
  transition_out: ke,
  update_slot_base: Se
} = window.__gradio__svelte__internal;
function qe(n) {
  let e, t;
  const l = (
    /*#slots*/
    n[1].default
  ), f = ue(
    l,
    n,
    /*$$scope*/
    n[0],
    null
  );
  return {
    c() {
      e = me("div"), f && f.c(), de(e, "class", "svelte-1hnfib2");
    },
    m(a, o) {
      we(a, e, o), f && f.m(e, null), t = !0;
    },
    p(a, [o]) {
      f && f.p && (!t || o & /*$$scope*/
      1) && Se(
        f,
        l,
        a,
        /*$$scope*/
        a[0],
        t ? ge(
          l,
          /*$$scope*/
          a[0],
          o,
          null
        ) : be(
          /*$$scope*/
          a[0]
        ),
        null
      );
    },
    i(a) {
      t || (ye(f, a), t = !0);
    },
    o(a) {
      ke(f, a), t = !1;
    },
    d(a) {
      a && re(e), f && f.d(a);
    }
  };
}
function Ce(n, e, t) {
  let { $$slots: l = {}, $$scope: f } = e;
  return n.$$set = (a) => {
    "$$scope" in a && t(0, f = a.$$scope);
  }, [f, l];
}
class Be extends ce {
  constructor(e) {
    super(), he(this, e, Ce, qe, ve, {});
  }
}
const {
  SvelteComponent: Ie,
  attr: A,
  check_outros: Te,
  create_component: ze,
  create_slot: je,
  destroy_component: De,
  detach: I,
  element: Ae,
  empty: Ee,
  get_all_dirty_from_scope: Le,
  get_slot_changes: Ne,
  group_outros: Oe,
  init: Ue,
  insert: T,
  mount_component: Fe,
  safe_not_equal: Ge,
  set_data: He,
  space: Je,
  text: Ke,
  toggle_class: v,
  transition_in: q,
  transition_out: z,
  update_slot_base: Me
} = window.__gradio__svelte__internal;
function E(n) {
  let e, t;
  return e = new Be({
    props: {
      $$slots: { default: [Pe] },
      $$scope: { ctx: n }
    }
  }), {
    c() {
      ze(e.$$.fragment);
    },
    m(l, f) {
      Fe(e, l, f), t = !0;
    },
    p(l, f) {
      const a = {};
      f & /*$$scope, info*/
      10 && (a.$$scope = { dirty: f, ctx: l }), e.$set(a);
    },
    i(l) {
      t || (q(e.$$.fragment, l), t = !0);
    },
    o(l) {
      z(e.$$.fragment, l), t = !1;
    },
    d(l) {
      De(e, l);
    }
  };
}
function Pe(n) {
  let e;
  return {
    c() {
      e = Ke(
        /*info*/
        n[1]
      );
    },
    m(t, l) {
      T(t, e, l);
    },
    p(t, l) {
      l & /*info*/
      2 && He(
        e,
        /*info*/
        t[1]
      );
    },
    d(t) {
      t && I(e);
    }
  };
}
function Qe(n) {
  let e, t, l, f;
  const a = (
    /*#slots*/
    n[2].default
  ), o = je(
    a,
    n,
    /*$$scope*/
    n[3],
    null
  );
  let _ = (
    /*info*/
    n[1] && E(n)
  );
  return {
    c() {
      e = Ae("span"), o && o.c(), t = Je(), _ && _.c(), l = Ee(), A(e, "data-testid", "block-info"), A(e, "class", "svelte-22c38v"), v(e, "sr-only", !/*show_label*/
      n[0]), v(e, "hide", !/*show_label*/
      n[0]), v(
        e,
        "has-info",
        /*info*/
        n[1] != null
      );
    },
    m(i, s) {
      T(i, e, s), o && o.m(e, null), T(i, t, s), _ && _.m(i, s), T(i, l, s), f = !0;
    },
    p(i, [s]) {
      o && o.p && (!f || s & /*$$scope*/
      8) && Me(
        o,
        a,
        i,
        /*$$scope*/
        i[3],
        f ? Ne(
          a,
          /*$$scope*/
          i[3],
          s,
          null
        ) : Le(
          /*$$scope*/
          i[3]
        ),
        null
      ), (!f || s & /*show_label*/
      1) && v(e, "sr-only", !/*show_label*/
      i[0]), (!f || s & /*show_label*/
      1) && v(e, "hide", !/*show_label*/
      i[0]), (!f || s & /*info*/
      2) && v(
        e,
        "has-info",
        /*info*/
        i[1] != null
      ), /*info*/
      i[1] ? _ ? (_.p(i, s), s & /*info*/
      2 && q(_, 1)) : (_ = E(i), _.c(), q(_, 1), _.m(l.parentNode, l)) : _ && (Oe(), z(_, 1, 1, () => {
        _ = null;
      }), Te());
    },
    i(i) {
      f || (q(o, i), q(_), f = !0);
    },
    o(i) {
      z(o, i), z(_), f = !1;
    },
    d(i) {
      i && (I(e), I(t), I(l)), o && o.d(i), _ && _.d(i);
    }
  };
}
function Re(n, e, t) {
  let { $$slots: l = {}, $$scope: f } = e, { show_label: a = !0 } = e, { info: o = void 0 } = e;
  return n.$$set = (_) => {
    "show_label" in _ && t(0, a = _.show_label), "info" in _ && t(1, o = _.info), "$$scope" in _ && t(3, f = _.$$scope);
  }, [a, o, l, f];
}
class Ve extends Ie {
  constructor(e) {
    super(), Ue(this, e, Re, Qe, Ge, { show_label: 0, info: 1 });
  }
}
const We = [
  { color: "red", primary: 600, secondary: 100 },
  { color: "green", primary: 600, secondary: 100 },
  { color: "blue", primary: 600, secondary: 100 },
  { color: "yellow", primary: 500, secondary: 100 },
  { color: "purple", primary: 600, secondary: 100 },
  { color: "teal", primary: 600, secondary: 100 },
  { color: "orange", primary: 600, secondary: 100 },
  { color: "cyan", primary: 600, secondary: 100 },
  { color: "lime", primary: 500, secondary: 100 },
  { color: "pink", primary: 600, secondary: 100 }
], L = {
  inherit: "inherit",
  current: "currentColor",
  transparent: "transparent",
  black: "#000",
  white: "#fff",
  slate: {
    50: "#f8fafc",
    100: "#f1f5f9",
    200: "#e2e8f0",
    300: "#cbd5e1",
    400: "#94a3b8",
    500: "#64748b",
    600: "#475569",
    700: "#334155",
    800: "#1e293b",
    900: "#0f172a",
    950: "#020617"
  },
  gray: {
    50: "#f9fafb",
    100: "#f3f4f6",
    200: "#e5e7eb",
    300: "#d1d5db",
    400: "#9ca3af",
    500: "#6b7280",
    600: "#4b5563",
    700: "#374151",
    800: "#1f2937",
    900: "#111827",
    950: "#030712"
  },
  zinc: {
    50: "#fafafa",
    100: "#f4f4f5",
    200: "#e4e4e7",
    300: "#d4d4d8",
    400: "#a1a1aa",
    500: "#71717a",
    600: "#52525b",
    700: "#3f3f46",
    800: "#27272a",
    900: "#18181b",
    950: "#09090b"
  },
  neutral: {
    50: "#fafafa",
    100: "#f5f5f5",
    200: "#e5e5e5",
    300: "#d4d4d4",
    400: "#a3a3a3",
    500: "#737373",
    600: "#525252",
    700: "#404040",
    800: "#262626",
    900: "#171717",
    950: "#0a0a0a"
  },
  stone: {
    50: "#fafaf9",
    100: "#f5f5f4",
    200: "#e7e5e4",
    300: "#d6d3d1",
    400: "#a8a29e",
    500: "#78716c",
    600: "#57534e",
    700: "#44403c",
    800: "#292524",
    900: "#1c1917",
    950: "#0c0a09"
  },
  red: {
    50: "#fef2f2",
    100: "#fee2e2",
    200: "#fecaca",
    300: "#fca5a5",
    400: "#f87171",
    500: "#ef4444",
    600: "#dc2626",
    700: "#b91c1c",
    800: "#991b1b",
    900: "#7f1d1d",
    950: "#450a0a"
  },
  orange: {
    50: "#fff7ed",
    100: "#ffedd5",
    200: "#fed7aa",
    300: "#fdba74",
    400: "#fb923c",
    500: "#f97316",
    600: "#ea580c",
    700: "#c2410c",
    800: "#9a3412",
    900: "#7c2d12",
    950: "#431407"
  },
  amber: {
    50: "#fffbeb",
    100: "#fef3c7",
    200: "#fde68a",
    300: "#fcd34d",
    400: "#fbbf24",
    500: "#f59e0b",
    600: "#d97706",
    700: "#b45309",
    800: "#92400e",
    900: "#78350f",
    950: "#451a03"
  },
  yellow: {
    50: "#fefce8",
    100: "#fef9c3",
    200: "#fef08a",
    300: "#fde047",
    400: "#facc15",
    500: "#eab308",
    600: "#ca8a04",
    700: "#a16207",
    800: "#854d0e",
    900: "#713f12",
    950: "#422006"
  },
  lime: {
    50: "#f7fee7",
    100: "#ecfccb",
    200: "#d9f99d",
    300: "#bef264",
    400: "#a3e635",
    500: "#84cc16",
    600: "#65a30d",
    700: "#4d7c0f",
    800: "#3f6212",
    900: "#365314",
    950: "#1a2e05"
  },
  green: {
    50: "#f0fdf4",
    100: "#dcfce7",
    200: "#bbf7d0",
    300: "#86efac",
    400: "#4ade80",
    500: "#22c55e",
    600: "#16a34a",
    700: "#15803d",
    800: "#166534",
    900: "#14532d",
    950: "#052e16"
  },
  emerald: {
    50: "#ecfdf5",
    100: "#d1fae5",
    200: "#a7f3d0",
    300: "#6ee7b7",
    400: "#34d399",
    500: "#10b981",
    600: "#059669",
    700: "#047857",
    800: "#065f46",
    900: "#064e3b",
    950: "#022c22"
  },
  teal: {
    50: "#f0fdfa",
    100: "#ccfbf1",
    200: "#99f6e4",
    300: "#5eead4",
    400: "#2dd4bf",
    500: "#14b8a6",
    600: "#0d9488",
    700: "#0f766e",
    800: "#115e59",
    900: "#134e4a",
    950: "#042f2e"
  },
  cyan: {
    50: "#ecfeff",
    100: "#cffafe",
    200: "#a5f3fc",
    300: "#67e8f9",
    400: "#22d3ee",
    500: "#06b6d4",
    600: "#0891b2",
    700: "#0e7490",
    800: "#155e75",
    900: "#164e63",
    950: "#083344"
  },
  sky: {
    50: "#f0f9ff",
    100: "#e0f2fe",
    200: "#bae6fd",
    300: "#7dd3fc",
    400: "#38bdf8",
    500: "#0ea5e9",
    600: "#0284c7",
    700: "#0369a1",
    800: "#075985",
    900: "#0c4a6e",
    950: "#082f49"
  },
  blue: {
    50: "#eff6ff",
    100: "#dbeafe",
    200: "#bfdbfe",
    300: "#93c5fd",
    400: "#60a5fa",
    500: "#3b82f6",
    600: "#2563eb",
    700: "#1d4ed8",
    800: "#1e40af",
    900: "#1e3a8a",
    950: "#172554"
  },
  indigo: {
    50: "#eef2ff",
    100: "#e0e7ff",
    200: "#c7d2fe",
    300: "#a5b4fc",
    400: "#818cf8",
    500: "#6366f1",
    600: "#4f46e5",
    700: "#4338ca",
    800: "#3730a3",
    900: "#312e81",
    950: "#1e1b4b"
  },
  violet: {
    50: "#f5f3ff",
    100: "#ede9fe",
    200: "#ddd6fe",
    300: "#c4b5fd",
    400: "#a78bfa",
    500: "#8b5cf6",
    600: "#7c3aed",
    700: "#6d28d9",
    800: "#5b21b6",
    900: "#4c1d95",
    950: "#2e1065"
  },
  purple: {
    50: "#faf5ff",
    100: "#f3e8ff",
    200: "#e9d5ff",
    300: "#d8b4fe",
    400: "#c084fc",
    500: "#a855f7",
    600: "#9333ea",
    700: "#7e22ce",
    800: "#6b21a8",
    900: "#581c87",
    950: "#3b0764"
  },
  fuchsia: {
    50: "#fdf4ff",
    100: "#fae8ff",
    200: "#f5d0fe",
    300: "#f0abfc",
    400: "#e879f9",
    500: "#d946ef",
    600: "#c026d3",
    700: "#a21caf",
    800: "#86198f",
    900: "#701a75",
    950: "#4a044e"
  },
  pink: {
    50: "#fdf2f8",
    100: "#fce7f3",
    200: "#fbcfe8",
    300: "#f9a8d4",
    400: "#f472b6",
    500: "#ec4899",
    600: "#db2777",
    700: "#be185d",
    800: "#9d174d",
    900: "#831843",
    950: "#500724"
  },
  rose: {
    50: "#fff1f2",
    100: "#ffe4e6",
    200: "#fecdd3",
    300: "#fda4af",
    400: "#fb7185",
    500: "#f43f5e",
    600: "#e11d48",
    700: "#be123c",
    800: "#9f1239",
    900: "#881337",
    950: "#4c0519"
  }
};
We.reduce(
  (n, { color: e, primary: t, secondary: l }) => ({
    ...n,
    [e]: {
      primary: L[e][t],
      secondary: L[e][l]
    }
  }),
  {}
);
const {
  SvelteComponent: Xe,
  append: N,
  attr: j,
  binding_callbacks: Ye,
  create_component: K,
  destroy_component: M,
  detach: P,
  element: O,
  init: Ze,
  insert: Q,
  listen: U,
  mount_component: R,
  run_all: pe,
  safe_not_equal: xe,
  set_data: $e,
  set_input_value: F,
  space: e0,
  text: t0,
  toggle_class: G,
  transition_in: V,
  transition_out: W
} = window.__gradio__svelte__internal;
function l0(n) {
  let e;
  return {
    c() {
      e = t0(
        /*label*/
        n[1]
      );
    },
    m(t, l) {
      Q(t, e, l);
    },
    p(t, l) {
      l & /*label*/
      2 && $e(
        e,
        /*label*/
        t[1]
      );
    },
    d(t) {
      t && P(e);
    }
  };
}
function n0(n) {
  let e, t, l, f, a, o, _, i;
  return t = new Ve({
    props: {
      show_label: (
        /*show_label*/
        n[8]
      ),
      info: (
        /*info*/
        n[6]
      ),
      $$slots: { default: [l0] },
      $$scope: { ctx: n }
    }
  }), {
    c() {
      e = O("label"), K(t.$$.fragment), l = e0(), f = O("input"), j(f, "type", "date"), f.disabled = a = !/*interactive*/
      n[10], j(f, "class", "svelte-c6v8zr"), j(e, "class", "svelte-c6v8zr"), G(
        e,
        "container",
        /*container*/
        n[9]
      );
    },
    m(s, u) {
      Q(s, e, u), R(t, e, null), N(e, l), N(e, f), n[15](f), F(
        f,
        /*value*/
        n[0]
      ), o = !0, _ || (i = [
        U(
          f,
          "input",
          /*input_input_handler*/
          n[16]
        ),
        U(
          f,
          "change",
          /*handle_change*/
          n[12]
        )
      ], _ = !0);
    },
    p(s, u) {
      const m = {};
      u & /*show_label*/
      256 && (m.show_label = /*show_label*/
      s[8]), u & /*info*/
      64 && (m.info = /*info*/
      s[6]), u & /*$$scope, label*/
      131074 && (m.$$scope = { dirty: u, ctx: s }), t.$set(m), (!o || u & /*interactive*/
      1024 && a !== (a = !/*interactive*/
      s[10])) && (f.disabled = a), u & /*value*/
      1 && F(
        f,
        /*value*/
        s[0]
      ), (!o || u & /*container*/
      512) && G(
        e,
        "container",
        /*container*/
        s[9]
      );
    },
    i(s) {
      o || (V(t.$$.fragment, s), o = !0);
    },
    o(s) {
      W(t.$$.fragment, s), o = !1;
    },
    d(s) {
      s && P(e), M(t), n[15](null), _ = !1, pe(i);
    }
  };
}
function f0(n) {
  let e, t;
  return e = new oe({
    props: {
      visible: (
        /*visible*/
        n[2]
      ),
      elem_id: (
        /*elem_id*/
        n[4]
      ),
      elem_classes: (
        /*elem_classes*/
        n[3]
      ),
      scale: (
        /*scale*/
        n[5]
      ),
      min_width: (
        /*min_width*/
        n[7]
      ),
      allow_overflow: !1,
      padding: !0,
      $$slots: { default: [n0] },
      $$scope: { ctx: n }
    }
  }), {
    c() {
      K(e.$$.fragment);
    },
    m(l, f) {
      R(e, l, f), t = !0;
    },
    p(l, [f]) {
      const a = {};
      f & /*visible*/
      4 && (a.visible = /*visible*/
      l[2]), f & /*elem_id*/
      16 && (a.elem_id = /*elem_id*/
      l[4]), f & /*elem_classes*/
      8 && (a.elem_classes = /*elem_classes*/
      l[3]), f & /*scale*/
      32 && (a.scale = /*scale*/
      l[5]), f & /*min_width*/
      128 && (a.min_width = /*min_width*/
      l[7]), f & /*$$scope, container, interactive, el, value, show_label, info, label*/
      134979 && (a.$$scope = { dirty: f, ctx: l }), e.$set(a);
    },
    i(l) {
      t || (V(e.$$.fragment, l), t = !0);
    },
    o(l) {
      W(e.$$.fragment, l), t = !1;
    },
    d(l) {
      M(e, l);
    }
  };
}
function i0(n, e, t) {
  let { value: l = null } = e, { value_is_output: f = !1 } = e, { label: a } = e, { visible: o = !0 } = e, { elem_classes: _ } = e, { elem_id: i } = e, { scale: s } = e, { info: u } = e, { min_width: m } = e, { show_label: h = !0 } = e, { container: y = !0 } = e, { interactive: k = !0 } = e, { gradio: b } = e, w;
  function S() {
    b.dispatch("change"), f || (b.dispatch("submit"), b.dispatch("input"));
  }
  function C(d) {
    Ye[d ? "unshift" : "push"](() => {
      w = d, t(11, w);
    });
  }
  function B() {
    l = this.value, t(0, l);
  }
  return n.$$set = (d) => {
    "value" in d && t(0, l = d.value), "value_is_output" in d && t(13, f = d.value_is_output), "label" in d && t(1, a = d.label), "visible" in d && t(2, o = d.visible), "elem_classes" in d && t(3, _ = d.elem_classes), "elem_id" in d && t(4, i = d.elem_id), "scale" in d && t(5, s = d.scale), "info" in d && t(6, u = d.info), "min_width" in d && t(7, m = d.min_width), "show_label" in d && t(8, h = d.show_label), "container" in d && t(9, y = d.container), "interactive" in d && t(10, k = d.interactive), "gradio" in d && t(14, b = d.gradio);
  }, n.$$.update = () => {
    n.$$.dirty & /*value*/
    1 && l === null && t(0, l = (/* @__PURE__ */ new Date()).toISOString().split("T")[0]), n.$$.dirty & /*value*/
    1 && S();
  }, [
    l,
    a,
    o,
    _,
    i,
    s,
    u,
    m,
    h,
    y,
    k,
    w,
    S,
    f,
    b,
    C,
    B
  ];
}
class a0 extends Xe {
  constructor(e) {
    super(), Ze(this, e, i0, f0, xe, {
      value: 0,
      value_is_output: 13,
      label: 1,
      visible: 2,
      elem_classes: 3,
      elem_id: 4,
      scale: 5,
      info: 6,
      min_width: 7,
      show_label: 8,
      container: 9,
      interactive: 10,
      gradio: 14
    });
  }
}
export {
  a0 as default
};
