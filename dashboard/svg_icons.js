/* ============================================================
   مكتبة أيقونات أبيلا - SVG على ستايل خطي ذهبي/بني فخم
   Abela SVG Icons Library — gold/brown line-art style
   ============================================================
   جميع الأيقونات بنفس النمط:
   - viewBox 24x24
   - fill: none, stroke: currentColor
   - stroke-width: 1.6
   - stroke-linecap/linejoin: round
   ============================================================ */

const SVG_PROPS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"';

// ============================================================
// أيقونات المستودعات (Warehouses)
// ============================================================
const ICONS_WAREHOUSE = {
  decorations: `<svg ${SVG_PROPS}><path d="M12 2v4M12 18v4M2 12h4M18 12h4M5 5l3 3M16 16l3 3M5 19l3-3M16 8l3-3"/><circle cx="12" cy="12" r="4"/></svg>`,
  accessories: `<svg ${SVG_PROPS}><path d="M12 2l1.6 5h5.4l-4.4 3.2 1.7 5.3L12 12.3 7.7 15.5l1.7-5.3L5 7h5.4z"/></svg>`,
  factory: `<svg ${SVG_PROPS}><path d="M3 21h18M3 21V11l5 3V11l5 3V11l5 3v7M7 21v-3M11 21v-3M15 21v-3M19 21v-3"/></svg>`,
  hospitality: `<svg ${SVG_PROPS}><path d="M5 3v8a3 3 0 003 3v7M8 3v8M19 3c-1.7 0-3 1.5-3 4v5h3M19 3v18"/></svg>`,
  purchasing: `<svg ${SVG_PROPS}><path d="M3 3h2.4l2 12.5a2 2 0 002 1.7h8.5a2 2 0 002-1.7L21 7H6"/><circle cx="9" cy="20" r="1.4"/><circle cx="18" cy="20" r="1.4"/></svg>`,
  risk: `<svg ${SVG_PROPS}><path d="M12 3l9 16H3z"/><path d="M12 10v5M12 17.5v.1"/></svg>`,
  factory_raw: `<svg ${SVG_PROPS}><rect x="3" y="8" width="18" height="13" rx="1.5"/><path d="M3 12h18M9 8V5l3-2 3 2v3"/></svg>`,
};

// ============================================================
// أيقونات تصنيفات الأكسسوارات والديكورات (Categories)
// ============================================================
const ICONS_CATEGORY = {
  // ـــ خلفيات وإطارات ـــ
  background: `<svg ${SVG_PROPS}><rect x="3" y="4" width="18" height="14" rx="1.5"/><path d="M3 14l4-4 4 4 3-3 7 7"/><circle cx="8" cy="9" r="1.4"/></svg>`,
  frame: `<svg ${SVG_PROPS}><rect x="3" y="3" width="18" height="18" rx="1"/><rect x="6" y="6" width="12" height="12" rx="0.5"/></svg>`,

  // ـــ أثاث ـــ
  entrance: `<svg ${SVG_PROPS}><rect x="5" y="3" width="14" height="18" rx="1"/><path d="M5 21h14M9 12h0.01M11 3v18"/></svg>`,
  door: `<svg ${SVG_PROPS}><rect x="5" y="3" width="14" height="18" rx="1"/><circle cx="15" cy="12" r="0.8"/></svg>`,
  console: `<svg ${SVG_PROPS}><path d="M3 8h18v3H3zM5 11v9M19 11v9M3 14h18"/></svg>`,
  table: `<svg ${SVG_PROPS}><path d="M3 9h18v3H3zM6 12v8M18 12v8"/></svg>`,
  chair: `<svg ${SVG_PROPS}><path d="M7 21v-3M17 21v-3M5 18h14M7 18V9c0-2 1-4 5-4s5 2 5 4v9"/></svg>`,
  sofa: `<svg ${SVG_PROPS}><path d="M3 13a2 2 0 012-2v-1a2 2 0 012-2h10a2 2 0 012 2v1a2 2 0 012 2v5h-2v-2H5v2H3z"/></svg>`,
  cushion: `<svg ${SVG_PROPS}><path d="M5 6c2-2 12-2 14 0 2 2 2 12 0 14-2 2-12 2-14 0-2-2-2-12 0-14z"/></svg>`,
  bed: `<svg ${SVG_PROPS}><path d="M3 18V8M21 18v-4M3 14h18M3 18h18M7 14V9c0-1 .5-2 2-2h6c1.5 0 2 1 2 2v5"/></svg>`,
  wardrobe: `<svg ${SVG_PROPS}><rect x="4" y="3" width="16" height="18" rx="1"/><path d="M12 3v18M9 12h-1M16 12h-1"/></svg>`,
  dress: `<svg ${SVG_PROPS}><path d="M9 3l3 3 3-3M9 3v3l-4 5 3 2-2 9h12l-2-9 3-2-4-5V3"/></svg>`,

  // ـــ إضاءة وتزيين ـــ
  light: `<svg ${SVG_PROPS}><path d="M9 18h6M10 21h4M12 3a6 6 0 00-3 11l1 2h4l1-2a6 6 0 00-3-11z"/></svg>`,
  candle: `<svg ${SVG_PROPS}><path d="M12 3c-1 1-2 2-2 3.5S11 9 12 9s2-1 2-2.5S13 4 12 3zM8 9h8v12H8z"/></svg>`,
  flower: `<svg ${SVG_PROPS}><circle cx="12" cy="12" r="2"/><path d="M12 10V5M12 14v5M10 12H5M14 12h5M9.5 9.5L6 6M14.5 9.5L18 6M9.5 14.5L6 18M14.5 14.5L18 18"/></svg>`,
  vase: `<svg ${SVG_PROPS}><path d="M9 3h6v3l1 3v9a3 3 0 01-3 3h-2a3 3 0 01-3-3V9l1-3z"/></svg>`,
  ornament: `<svg ${SVG_PROPS}><circle cx="12" cy="14" r="6"/><path d="M12 8V4M10 4h4"/></svg>`,

  // ـــ ضيافة ـــ
  food: `<svg ${SVG_PROPS}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>`,
  drink: `<svg ${SVG_PROPS}><path d="M6 4h12l-2 16H8z"/><path d="M7 9h10"/></svg>`,
  cup: `<svg ${SVG_PROPS}><path d="M5 6h12v9a4 4 0 01-4 4H9a4 4 0 01-4-4z"/><path d="M17 9h2a2 2 0 010 4h-2"/></svg>`,
  plate: `<svg ${SVG_PROPS}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="6"/></svg>`,

  // ـــ توزيعات وهدايا ـــ
  gift: `<svg ${SVG_PROPS}><rect x="3" y="9" width="18" height="12" rx="1"/><path d="M12 9v12M3 13h18M8 9c-1.5 0-3-1-3-3s1.5-3 3-3c2 0 4 4 4 6 0-2 2-6 4-6 1.5 0 3 1 3 3s-1.5 3-3 3"/></svg>`,
  box: `<svg ${SVG_PROPS}><path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/></svg>`,
  ribbon: `<svg ${SVG_PROPS}><path d="M12 4v6M9 6c0-1 1-2 3-2s3 1 3 2-2 2-3 2-3-1-3-2zM6 10h12v8l-6-4-6 4z"/></svg>`,

  // ـــ نباتات ـــ
  plant: `<svg ${SVG_PROPS}><path d="M9 21V11M9 11c-3 0-5-2-5-5 3 0 5 2 5 5zM9 11c0-3 2-5 5-5 0 3-2 5-5 5zM6 21h6"/></svg>`,

  // ـــ مفروشات ـــ
  carpet: `<svg ${SVG_PROPS}><rect x="3" y="6" width="18" height="12" rx="1"/><path d="M6 9h12M6 12h12M6 15h12"/></svg>`,
  curtain: `<svg ${SVG_PROPS}><path d="M4 3h16v2H4zM6 5v16M10 5v16M14 5v16M18 5v16"/></svg>`,
  fabric: `<svg ${SVG_PROPS}><path d="M3 21l3-3 3 3 3-3 3 3 3-3 3 3V5l-3-2-3 2-3-2-3 2-3-2-3 2z"/></svg>`,

  // ـــ تصنيع ـــ
  tool: `<svg ${SVG_PROPS}><path d="M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-3 3-2-2z"/></svg>`,
  paint: `<svg ${SVG_PROPS}><path d="M19 7c0 2-2 3-4 3H8a3 3 0 00-3 3v3a3 3 0 003 3h2v-2a2 2 0 014 0v2h2a3 3 0 003-3V7z"/></svg>`,
  wood: `<svg ${SVG_PROPS}><rect x="3" y="3" width="18" height="18" rx="1"/><path d="M5 7c2 0 5-1 7 0s4 1 7 0M5 12c2 0 5-1 7 0s4 1 7 0M5 17c2 0 5-1 7 0s4 1 7 0"/></svg>`,
  nail: `<svg ${SVG_PROPS}><path d="M12 3l5 5h-3v13h-4V8H7z"/></svg>`,
  wire: `<svg ${SVG_PROPS}><path d="M3 12c2-3 4-3 5 0s2 6 4 6 3-3 4-6 2-3 5 0"/></svg>`,
  metal: `<svg ${SVG_PROPS}><path d="M5 4l3 16h8l3-16M7 9h10M7 14h10"/></svg>`,
  acrylic: `<svg ${SVG_PROPS}><rect x="4" y="4" width="16" height="16" rx="1"/><path d="M8 4v16M16 4v16"/></svg>`,
  adhesive: `<svg ${SVG_PROPS}><path d="M9 3v6l-2 2v9h10v-9l-2-2V3z"/></svg>`,
  consumable: `<svg ${SVG_PROPS}><circle cx="12" cy="12" r="8"/><path d="M9 9h6M9 12h6M9 15h4"/></svg>`,

  // ـــ افتراضي ـــ
  default: `<svg ${SVG_PROPS}><rect x="4" y="4" width="16" height="16" rx="1.5"/><path d="M8 12h8M12 8v8"/></svg>`,
};

// ============================================================
// مطابقة اسم التصنيف (عربي) → مفتاح الأيقونة
// ============================================================
const CATEGORY_NAME_MAP = [
  // خلفيات
  [/خلفية\s*سرير/, 'bed'],
  [/خلفية\s*ضياف/, 'plate'],
  [/خلفية\s*توزيع/, 'gift'],
  [/خلفية\s*كوش/, 'cushion'],
  [/خلفي/, 'background'],
  [/إطار|اطار|frame/i, 'frame'],

  // أثاث
  [/مدخل|بوابة/, 'entrance'],
  [/كونسول|console/i, 'console'],
  [/طاول|table/i, 'table'],
  [/كرس|كراس|chair/i, 'chair'],
  [/صوف|كنب|sofa/i, 'sofa'],
  [/كوش|cushion/i, 'cushion'],
  [/سرير|bed/i, 'bed'],
  [/دولاب|wardrobe|عبا/i, 'wardrobe'],
  [/فستان|عبا|dress/i, 'dress'],

  // إضاءة وتزيين
  [/إضاء|اضاء|light|lamp/i, 'light'],
  [/شمع|candle/i, 'candle'],
  [/ورد|زهر|flower/i, 'flower'],
  [/فاز|vase/i, 'vase'],
  [/زين|تزيين|ornament/i, 'ornament'],

  // ضيافة
  [/طعام|أكل|اكل|food/i, 'food'],
  [/مشروب|عصير|drink/i, 'drink'],
  [/كوب|كأس|كاس|cup/i, 'cup'],
  [/طبق|صحن|plate/i, 'plate'],

  // توزيعات
  [/توزيع|هدية|gift/i, 'gift'],
  [/علب|صندوق|box/i, 'box'],
  [/شريط|ربون|ribbon/i, 'ribbon'],

  // نباتات ومفروشات
  [/نبات|شجر|plant/i, 'plant'],
  [/سجاد|carpet|بساط/i, 'carpet'],
  [/ستار|curtain/i, 'curtain'],
  [/قماش|fabric/i, 'fabric'],

  // تصنيع
  [/أدا|اداة|tool/i, 'tool'],
  [/بوي|دهان|paint/i, 'paint'],
  [/خشب|wood/i, 'wood'],
  [/مسما|برغي|nail/i, 'nail'],
  [/سلك|wire|LED|أسلاك/i, 'wire'],
  [/استانلس|حديد|metal/i, 'metal'],
  [/أكريلك|اكريلك|acrylic/i, 'acrylic'],
  [/لاص|adhesive|غراء/i, 'adhesive'],
  [/مستهلك|consumable/i, 'consumable'],
];

/**
 * يرجع SVG markup للتصنيف بناءً على اسمه
 * @param {string} name - اسم التصنيف بالعربي
 * @param {string} fallback - أيقونة بديلة لو ما لقى
 */
function categoryIcon(name, fallback = 'default') {
  if (!name) return ICONS_CATEGORY[fallback] || ICONS_CATEGORY.default;
  for (const [regex, key] of CATEGORY_NAME_MAP) {
    if (regex.test(name)) return ICONS_CATEGORY[key] || ICONS_CATEGORY.default;
  }
  return ICONS_CATEGORY[fallback] || ICONS_CATEGORY.default;
}

/**
 * يرجع SVG markup للمستودع
 */
function warehouseIcon(key) {
  return ICONS_WAREHOUSE[key] || ICONS_WAREHOUSE.decorations;
}

// إتاحة عالمية
if (typeof window !== 'undefined') {
  window.categoryIcon = categoryIcon;
  window.warehouseIcon = warehouseIcon;
  window.ICONS_WAREHOUSE = ICONS_WAREHOUSE;
  window.ICONS_CATEGORY = ICONS_CATEGORY;
}
