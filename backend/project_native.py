"""
ملف المشروع (/project) — تطبيق الدليل الإجرائي ومخطط سير العمل داخل المنصة
==========================================================================
لكل مناسبة (أمر تشغيل O####):
  · استمارة احتياجات العميل (2.A)
  · القائمة الشاملة Master Checklist — 6 أقسام من D-30 إلى D+7 بمسؤول وموعد ودليل إنجاز
  · سجل المخاطر RG.1
  · نقاط الاعتماد وفحص الجودة واعتماد التسليم (7.A / نموذج اعتماد التسليم)
  · طلبات التغيير (ملحق أ — 4 مستويات حسب النسبة)
  · الشكاوى والمشاكل والتصعيد (ملحقا ب وج)
  · الإقفال: سجل التلفيات + تقرير الإغلاق (8.B) + الدروس المستفادة
  · استبيان رضا العميل (11.A) برابط عام للعميل + NPS
ومؤشرات الأداء مقابل الأهداف (رضا 95% · NPS ≥ 70 · ربح ≥ 35% · شكاوى ≤ 5% · إقفال ≤ 48 ساعة · تحصيل ≥ 95%).
قاعدة: لا اعتماد لخطة العمل قبل استلام العربون (تُفحص في wpgen_routes.api_approve عبر deposit_ok).
"""
import json, re, uuid, datetime, secrets

DEFAULTS = {'min_budget': 20000, 'min_margin': 35, 'deposit_pct': 50}
TIERS = ['VIP', 'Gold', 'Standard']

# (القسم، الإزاحة بالأيام من يوم المناسبة، البنود [(العنوان، المسؤول)])
CHECKLIST = [
    ('التخطيط', -15, [
        ('اعتماد الخطة الزمنية الرئيسية للمشروع', 'العمليات'), ('اعتماد التصميم النهائي من العميل', 'التصميم'),
        ('اعتماد قائمة الخامات والألوان', 'التصميم'), ('اعتماد قائمة الموردين الأساسيين', 'المشتريات'),
        ('إصدار أوامر التشغيل لكل فريق', 'العمليات'), ('تسليم خطة المصنع لقائد فريق التنفيذ', 'المصنع'),
        ('تسليم خطة المستودع — الديكورات', 'المستودع'), ('تسليم خطة المستودع — الإكسسوارات', 'الكماليات'),
        ('تسليم خطة الضيافة لفريق الضيافة', 'الضيافة'), ('تسليم خطة المشتريات لقسم المشتريات', 'المشتريات'),
        ('تسليم خطة التوثيق لفريق التصوير', 'التوثيق'), ('تأكيد تواريخ الدفعات المالية المتبقية', 'المالية'),
        ('اعتماد سجل المخاطر للمشروع', 'العمليات'), ('إنشاء مجموعة الواتساب التشغيلية للمشروع', 'خدمة العملاء'),
        ('إعداد ملف المشروع في المنصة', 'العمليات')]),
    ('التجهيز', -7, [
        ('بدء تصنيع القطع الخاصة في المصنع', 'المصنع'), ('متابعة تقدم التصنيع اليومي', 'المصنع'),
        ('إصدار طلبات الشراء للمواد الخارجية', 'المشتريات'), ('تأكيد طلبيات الزهور مع الموردين', 'المشتريات'),
        ('تأكيد طلبيات الأقمشة الخاصة', 'المشتريات'), ('تأكيد طلبية الكيكة الرئيسية', 'الضيافة'),
        ('تأكيد طلبيات الإضاءة المتخصصة', 'المشتريات'), ('تأكيد عقد التصوير مع المصور', 'التوثيق'),
        ('تأكيد فريق الموسيقى/DJ (إن وُجد)', 'خدمة العملاء'), ('حجز السيارات لنقل المعدات', 'التشغيل'),
        ('تأكيد الأذونات الخاصة بالموقع', 'خدمة العملاء'), ('زيارة معاينة للموقع وتوثيقها', 'الإشراف'),
        ('اختبار أولي للخامات الواردة', 'المصنع'), ('إعداد قائمة الجرد الأولية', 'المستودع'),
        ('تذكير العميل بالدفعة الثانية', 'المالية')]),
    ('ما قبل التنفيذ', -1, [
        ('اختبار العينات النهائي في المستودع', 'المستودع'), ('اختبار جميع الإضاءات', 'التشغيل'),
        ('اختبار جودة الطباعة (إن وُجدت)', 'المصنع'), ('اختبار سلامة الديكورات الكبيرة', 'المصنع'),
        ('اعتماد جميع العينات من مدير التشغيل', 'العمليات'), ('إعداد جدول يوم التنفيذ', 'العمليات'),
        ('اعتماد جدول يوم التنفيذ من مدير التشغيل', 'العمليات'), ('توزيع جدول يوم التنفيذ على قادة الفِرَق', 'العمليات'),
        ('عقد اجتماع ما قبل التنفيذ (72 ساعة)', 'العمليات'), ('مراجعة سجل المخاطر وتفعيل خطط الاستجابة', 'العمليات'),
        ('تحضير حقيبة الطوارئ الميدانية', 'الإشراف'), ('تحديث قائمة جهات الاتصال السريعة', 'الإشراف'),
        ('تأكيد فريق الطوارئ (Standby)', 'الإشراف'), ('استلام الدفعة النهائية من العميل', 'المالية'),
        ('إصدار الفاتورة النهائية', 'المالية'), ('تذكير العميل بتفاصيل اليوم', 'خدمة العملاء')]),
    ('يوم التجهيز', -1, [
        ('وصول الفريق للمستودع في الموعد', 'التشغيل'), ('إجراء جرد كامل للمعدات', 'المستودع'),
        ('مطابقة الجرد بقائمة المشروع', 'المستودع'), ('تجهيز السيارات حسب التسلسل المعتمد', 'التشغيل'),
        ('تثبيت الديكور بشكل آمن داخل السيارات', 'التشغيل'), ('اختبار نهائي للإضاءات قبل التحميل', 'التشغيل'),
        ('اختبار نهائي للطباعة قبل التحميل', 'المصنع'), ('تجهيز القائمة الشاملة المطبوعة لكل قائد', 'العمليات'),
        ('تجهيز هويات الفريق (إن لزم)', 'الإشراف'), ('التواصل مع إدارة الموقع لتأكيد الوصول', 'خدمة العملاء'),
        ('إعداد قائمة الفريق المشاركين بالاسم', 'الإشراف'), ('فحص حالة جميع المعدات الكهربائية', 'التشغيل'),
        ('إعداد منطقة العمل في المستودع', 'المستودع'), ('اعتماد التحميل النهائي من مدير التشغيل', 'العمليات')]),
    ('يوم التنفيذ', 0, [
        ('وصول مدير التشغيل لمعاينة الموقع المبكر', 'العمليات'), ('وصول السيارة الأولى — الخلفيات والأرضيات', 'التشغيل'),
        ('تركيب الخلفيات', 'التشغيل'), ('تركيب الإضاءات', 'التشغيل'), ('تركيب الديكور الرئيسي', 'الإشراف'),
        ('تركيب الإكسسوارات والتفاصيل', 'الإشراف'), ('وصول فريق الضيافة وبدء التجهيز', 'الضيافة'),
        ('تجهيز الكيكة الرئيسية', 'الضيافة'), ('اللمسات النهائية (الورود الطازجة، العطر)', 'الإشراف'),
        ('تصحيح ملاحظات فحص الجودة', 'الإشراف'), ('إخلاء الموقع من الفِرَق إلا التوثيق', 'الإشراف'),
        ('تواجد فريق Standby في الكواليس', 'الإشراف'), ('التصوير الاحترافي خلال الحفل', 'التوثيق'),
        ('متابعة سير الحفل وحل الطوارئ', 'العمليات')]),
    ('ما بعد التنفيذ', 7, [
        ('فك الديكور بعد انصراف آخر ضيف', 'التشغيل'), ('تغليف القطع القابلة لإعادة الاستخدام', 'التشغيل'),
        ('تحميل المعدات في سيارات الشركة', 'التشغيل'), ('تنظيف الموقع وتسليمه', 'الإشراف'),
        ('العودة للمستودع وتنزيل المعدات', 'المستودع'), ('إجراء جرد كامل ومقارنة بالقائمة الأصلية', 'المستودع'),
        ('تسجيل التلفيات في سجل التلفيات', 'المستودع'), ('تخزين القطع السليمة في مواقعها', 'المستودع'),
        ('إصلاح القطع التي تحتاج صيانة بسيطة', 'المصنع'), ('إرسال رسالة شكر للعميل خلال 24 ساعة', 'خدمة العملاء'),
        ('إرسال مقطع تشويقي للعميل (Reels)', 'التوثيق'), ('إرسال استبيان رضا العميل', 'خدمة العملاء'),
        ('معالجة الصور والفيديوهات', 'التوثيق'), ('تسليم المواد المصورة كاملة (خلال 72 ساعة)', 'التوثيق'),
        ('نشر محتوى تسويقي (بعد إذن العميل)', 'التسويق'), ('عقد جلسة التقييم الداخلي (Post-Mortem)', 'العمليات'),
        ('إعداد تقرير إغلاق المشروع', 'العمليات'), ('تحديث الدروس المستفادة', 'العمليات'),
        ('إغلاق ملف المشروع في المنصة', 'العمليات'), ('إضافة العميل لقائمة المتابعة', 'خدمة العملاء')]),
]
# أعمق موعد للبند داخل قسم «ما بعد التنفيذ»: بعض البنود خلال 24 ساعة
DUE_OVERRIDE = {'إرسال رسالة شكر للعميل خلال 24 ساعة': 1, 'إرسال استبيان رضا العميل': 1, 'فك الديكور بعد انصراف آخر ضيف': 0,
                'تسجيل التلفيات في سجل التلفيات': 1, 'تسليم المواد المصورة كاملة (خلال 72 ساعة)': 3, 'إعداد تقرير إغلاق المشروع': 2,
                'إغلاق ملف المشروع في المنصة': 2, 'إجراء جرد كامل ومقارنة بالقائمة الأصلية': 1}

DEFAULT_RISKS = [
    ('تأخر مورد رئيسي', 'متوسطة', 'عالٍ', 'مورد بديل + اتفاق إطاري + تنبيه قبل 72 ساعة'),
    ('انقطاع الكهرباء في الموقع', 'منخفضة', 'حرج', 'مولد احتياطي + بطاريات للإضاءة الأساسية'),
    ('غياب موظف رئيسي يوم التنفيذ', 'متوسطة', 'عالٍ', 'تغطية مزدوجة لكل دور حرج'),
    ('خامات معيبة عند الفتح', 'متوسطة', 'متوسط', 'اختبار عينات قبل التنفيذ بـ 48 ساعة'),
    ('تغيير العميل المتأخر', 'عالية', 'متوسط', 'نموذج طلب تغيير + سياسة سعر/زمن واضحة'),
    ('وصول الضيوف المبكر', 'عالية', 'متوسط', 'تجهيز كامل قبل الموعد المعلن بساعتين'),
    ('تلف ديكور أثناء النقل', 'منخفضة', 'متوسط', 'قطع احتياطية + تأمين على المعدات'),
]

GATES = ['اعتماد الخلفيات', 'اعتماد الإضاءات', 'اعتماد الديكور الرئيسي', 'فحص الجودة الأول', 'فحص الجودة النهائي']
QC_ITEMS = ['نظافة الموقع بالكامل', 'ضبط زوايا الديكور بدقة', 'اختبار جميع الإضاءات', 'ترتيب الإكسسوارات وتفاصيلها',
            'الورود الطازجة في موضعها', 'جاهزية طاولة الكيك الرئيسية', 'تجهيز ركن الضيافة بالكامل', 'اختبار الصوت والمؤثرات (إن وُجدت)',
            'إخفاء الأسلاك والكواليس', 'العطور والروائح متوازنة', 'الإضاءة بالحرارة المعتمدة', 'اختفاء أي عيوب بصرية واضحة',
            'جاهزية فريق Standby', 'إخلاء الموقع من فضلات التركيب', 'اختبار التصوير الاحترافي']
SIGNERS = ['مدير التشغيل', 'مدير المشروع', 'ممثل الإدارة']

NEEDS_FIELDS = [  # (المفتاح، العنوان، النوع، الخيارات)
    ('guests', 'عدد الضيوف المتوقع', 'num', None),
    ('budget', 'الميزانية المتوقعة (ر.س)', 'num', None),
    ('vision', 'وصف العميل لرؤيته بكلماته', 'text', None),
    ('mood', 'الجو العام', 'multi', ['هادئ', 'مفعم بالحياة', 'كلاسيكي', 'عصري', 'ملكي', 'بسيط أنيق', 'ريفي', 'بوهيمي', 'بحري', 'حالم', 'صباحي', 'مسائي']),
    ('theme', 'الثيم الأساسي', 'text', None),
    ('refs', 'المراجع البصرية', 'multi', ['صور Pinterest', 'مرجع Instagram', 'ألبوم خاص', 'صور حفلات سابقة', 'لا توجد مراجع — التصميم من أبيلا']),
    ('refs_note', 'روابط/تفاصيل المراجع', 'text', None),
    ('palette', 'لوحة الألوان', 'text', None),
    ('fabrics', 'الأقمشة', 'text', None),
    ('flowers', 'الورود', 'text', None),
    ('lighting', 'الإضاءة', 'multi', ['دافئة', 'باردة', 'مزيج', 'ثريات معلقة', 'سلاسل LED', 'إضاءة ملونة', 'شموع زخرفية', 'Spot Lights', 'بروجكترات']),
    ('lighting_note', 'ملاحظات الإضاءة', 'text', None),
    ('hospitality', 'الضيافة والطعام', 'text', None),
    ('extras', 'عناصر خاصة', 'multi', ['منطقة تصوير (Photo Booth)', 'ركن الهدايا والتذكارات', 'ركن الأم والمولود', 'موسيقى حية / DJ',
                                      'تصوير احترافي', 'تصوير فيديو + ريلز', 'منسق حفل (MC)', 'شاشة عرض', 'فعاليات تفاعلية', 'ركن للأطفال']),
    ('extras_note', 'تفاصيل إضافية', 'text', None),
    ('alerts', 'ملاحظات وتنبيهات خاصة (حساسية، خصوصية، توقيت…)', 'text', None),
]

CHANGE_LEVELS = [  # (المستوى، الحد الأعلى للنسبة، المعتمِد)
    ('بسيط', 0, 'مدير المشروع'), ('متوسط', 10, 'مدير العمليات'), ('جوهري', 30, 'الإدارة'), ('جذري', 1e9, 'المالك'),
]
ISSUE_TYPES = ['شكوى عميل', 'مشكلة تشغيلية', 'تصعيد']
SEVERITY = {  # المهلة بالساعات: استجابة / حل
    'منخفضة': (24, 168), 'متوسطة': (4, 72), 'عالية': (1, 24), 'حرجة': (0.25, 4)}


# ───────────────────────── أدوات ─────────────────────────
def now():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime('%Y-%m-%d %H:%M')


def today():
    return now()[:10]


def add_d(d, n):
    return (datetime.date.fromisoformat(d[:10]) + datetime.timedelta(days=n)).isoformat()


def t_(v):
    return '' if v is None else str(v).strip()


def r2(x):
    return round(float(x or 0) + 1e-9, 2)


def setting(conn, k):
    r = conn.execute("SELECT value FROM settings WHERE key=?", ('prj_' + k,)).fetchone()
    try:
        return float(r[0]) if r and r[0] not in (None, '') else DEFAULTS[k]
    except Exception:
        return DEFAULTS[k]


def init_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS prj_needs (O TEXT PRIMARY KEY, data_json TEXT, client_ok TEXT, by_name TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS prj_checklist (id INTEGER PRIMARY KEY AUTOINCREMENT, O TEXT, sec TEXT, n INTEGER, title TEXT, owner TEXT,
        due TEXT, status TEXT DEFAULT 'todo', done_at TEXT, done_by TEXT, evidence TEXT, note TEXT, custom INTEGER DEFAULT 0);
    CREATE INDEX IF NOT EXISTS idx_prj_cl_o ON prj_checklist(O);
    CREATE TABLE IF NOT EXISTS prj_risks (id INTEGER PRIMARY KEY AUTOINCREMENT, O TEXT, risk TEXT, prob TEXT, impact TEXT, response TEXT,
        owner TEXT, status TEXT DEFAULT 'مفتوحة', by_name TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS prj_qc (O TEXT PRIMARY KEY, gates_json TEXT, items_json TEXT, signs_json TEXT, updated TEXT);
    CREATE TABLE IF NOT EXISTS prj_changes (id INTEGER PRIMARY KEY AUTOINCREMENT, O TEXT, descr TEXT, kind TEXT, amount REAL, pct REAL,
        level TEXT, approver TEXT, status TEXT DEFAULT 'بانتظار الاعتماد', decided_by TEXT, decided_at TEXT, by_name TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS prj_issues (id INTEGER PRIMARY KEY AUTOINCREMENT, O TEXT, type TEXT, severity TEXT, descr TEXT, owner TEXT,
        status TEXT DEFAULT 'مفتوحة', ack_at TEXT, resolved_at TEXT, resolution TEXT, by_name TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS prj_damages (id INTEGER PRIMARY KEY AUTOINCREMENT, O TEXT, item TEXT, qty REAL, cause TEXT, cost REAL,
        action TEXT, by_name TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS prj_close (O TEXT PRIMARY KEY, lessons TEXT, team_eval TEXT, report_json TEXT, closed_by TEXT, closed_at TEXT);
    CREATE TABLE IF NOT EXISTS prj_survey (token TEXT PRIMARY KEY, O TEXT, created_at TEXT, created_by TEXT, answered_at TEXT, data_json TEXT,
        csat INTEGER, nps INTEGER);
    CREATE INDEX IF NOT EXISTS idx_prj_sv_o ON prj_survey(O);
    """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(customers)")]
    if 'tier' not in cols:
        conn.execute("ALTER TABLE customers ADD COLUMN tier TEXT")
    conn.commit()


# ───────────────────────── المشاريع ─────────────────────────
def _projects(conn, where='', params=()):
    """المناسبات ذات أمر التشغيل مع تاريخها (المؤكد أولاً) وبيانات العميل"""
    conf = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT O, C, Q FROM opn_orders WHERE COALESCE(O,'')<>''")} \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='opn_orders'").fetchone() else {}
    rows = conn.execute(f"""SELECT e.id, e.operation_order O, e.contract_code B, e.title, e.event_type, e.event_date, e.actual_date, e.status,
                                   e.venue_name, e.total_price, e.paid_amount, e.cost_total, e.profit, e.customer_id,
                                   c.full_name client, c.phone, c.tier
                            FROM events e LEFT JOIN customers c ON c.id=e.customer_id
                            WHERE COALESCE(e.operation_order,'') NOT IN ('', 'O1001') AND COALESCE(e.is_test,0)=0 {where}""", params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        c, q = conf.get(d['O'], ('', ''))
        d['confirmed'] = t_(d['actual_date']) or t_(c)
        d['date'] = d['confirmed'] or t_(d['event_date'])
        d['Q'] = t_(q)
        out.append(d)
    return out


def deposit_info(conn, O=None, Q=None):
    """هل استُلم العربون؟ (أي مبلغ مستلم ≥ نسبة العربون من قيمة العقد، ومرن: أي دفعة تكفي لو النسبة غير معروفة)"""
    total = paid = 0.0
    if O:
        e = conn.execute("SELECT total_price, paid_amount, contract_code FROM events WHERE operation_order=?", (O,)).fetchone()
        if e:
            total, paid = float(e[0] or 0), float(e[1] or 0)
            if e[2]:
                gp = conn.execute("SELECT COALESCE(SUM(amount),0) FROM gen_payments WHERE contract_code=?", (e[2],)).fetchone()[0]
                paid = max(paid, float(gp or 0))
    if Q:
        q = conn.execute("SELECT total_with_vat, gen_received, contract_code FROM quotes WHERE quote_code=?", (Q,)).fetchone()
        if q:
            total = total or float(q[0] or 0)
            paid = max(paid, float(q[1] or 0))
            gp = conn.execute("SELECT COALESCE(SUM(amount),0) FROM gen_payments WHERE quote_code=? OR (contract_code<>'' AND contract_code=?)",
                              (Q, q[2] or '#')).fetchone()[0]
            paid = max(paid, float(gp or 0))
    need = total * setting(conn, 'deposit_pct') / 100
    ok = (paid >= need - 1) if total else paid > 0
    return {'total': r2(total), 'paid': r2(paid), 'need': r2(need), 'ok': bool(ok and paid > 0)}


def deposit_ok(conn, Q):
    o = conn.execute("SELECT O FROM opn_orders WHERE Q=?", (Q,)).fetchone() if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='opn_orders'").fetchone() else None
    return deposit_info(conn, O=(o[0] if o else None), Q=Q)


def ensure_checklist(conn, O, date):
    if conn.execute("SELECT 1 FROM prj_checklist WHERE O=? LIMIT 1", (O,)).fetchone():
        return False
    n = 0
    for sec, off, items in CHECKLIST:
        for title, owner in items:
            n += 1
            due = add_d(date, DUE_OVERRIDE.get(title, off)) if date else ''
            if due and due < today():   # ملف أُنشئ متأخراً: البنود الفائتة تستحق اليوم بدل ما تظهر متأخرة من أول يوم
                due = today()
            conn.execute("INSERT INTO prj_checklist (O, sec, n, title, owner, due) VALUES (?,?,?,?,?,?)", (O, sec, n, title, owner, due))
    for risk, p, i, resp in DEFAULT_RISKS:
        conn.execute("INSERT INTO prj_risks (O, risk, prob, impact, response, owner, by_name, at) VALUES (?,?,?,?,?,?,?,?)",
                     (O, risk, p, i, resp, 'مدير التشغيل', 'القالب', now()))
    return True


def redate_checklist(conn, O, date):
    """إعادة حساب مواعيد البنود غير المنجزة لو تغيّر تاريخ المناسبة"""
    if not date:
        return
    offs = {title: DUE_OVERRIDE.get(title, off) for sec, off, items in CHECKLIST for title, _ in items}
    for r in conn.execute("SELECT id, title, due FROM prj_checklist WHERE O=? AND custom=0 AND status<>'done'", (O,)).fetchall():
        if r[1] in offs:
            nd = max(add_d(date, offs[r[1]]), min(r[2] or today(), today()))
            if nd != r[2]:
                conn.execute("UPDATE prj_checklist SET due=? WHERE id=?", (nd, r[0]))


def sync(conn):
    """يجهّز ملف المشروع تلقائياً للمناسبات القادمة خلال 45 يوم والجارية، ويحدّث المواعيد"""
    import sqlite3
    rf = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        return _sync(conn)
    finally:
        conn.row_factory = rf


def _sync(conn):
    init_tables(conn)
    t = today()
    n = 0
    for p in _projects(conn, "AND e.status NOT IN ('cancelled','lead','quoted')"):
        if not p['date']:
            continue
        if t <= p['date'] <= add_d(t, 45):
            if ensure_checklist(conn, p['O'], p['date']):
                n += 1
            else:
                redate_checklist(conn, p['O'], p['date'])
    conn.commit()
    return n


def _progress(conn):
    cl = {}
    for r in conn.execute("""SELECT O, COUNT(*) n, SUM(status='done') d, SUM(status<>'done' AND due<>'' AND due<?) late
                             FROM prj_checklist GROUP BY O""", (today(),)):
        cl[r[0]] = {'n': r[1], 'done': r[2] or 0, 'late': r[3] or 0}
    return cl


def _status_of(conn, p, cl, extra):
    O = p['O']
    c = cl.get(O)
    flags = []
    t = today()
    if not p['confirmed'] and p['date'] and p['date'] < t and p['status'] not in ('completed', 'cancelled'):
        flags.append('تجاوز المتوقع والموعد غير مؤكد')
    if c and c['late']:
        flags.append(f"{c['late']} بند متأخر")
    if extra['issues'].get(O):
        flags.append(f"{extra['issues'][O]} شكوى/مشكلة مفتوحة")
    if p['date'] and p['date'] < t and p['status'] == 'completed' and O not in extra['closed']:
        if p['date'] <= add_d(t, -2):
            flags.append('لم يُقفل خلال 48 ساعة')
    dep = None
    if p['status'] not in ('completed', 'cancelled'):
        di = deposit_info(conn, O=O)
        dep = di['ok']
        if not di['ok']:
            flags.append('العربون لم يُستلم — لا تخطيط')
    tv = float(p['total_price'] or 0) / 1.15
    if tv and tv < setting(conn, 'min_budget'):
        flags.append('أقل من الحد الأدنى للميزانية')
    return flags, dep


def list_projects(conn, scope='active'):
    t = today()
    if scope == 'all':
        ps = _projects(conn, "AND e.status<>'cancelled'")
    elif scope == 'closing':
        ps = [p for p in _projects(conn, "AND e.status='completed'") if p['date'] and p['date'] >= add_d(t, -60)]
    else:
        ps = [p for p in _projects(conn, "AND e.status NOT IN ('cancelled','lead','quoted')")
              if p['date'] and (p['date'] >= add_d(t, -14) or p['status'] not in ('completed',))]
    cl = _progress(conn)
    extra = {
        'issues': {r[0]: r[1] for r in conn.execute("SELECT O, COUNT(*) FROM prj_issues WHERE status<>'محلولة' GROUP BY O")},
        'closed': {r[0] for r in conn.execute("SELECT O FROM prj_close WHERE closed_at IS NOT NULL")},
        'survey': {r[0]: (r[1], r[2]) for r in conn.execute("SELECT O, MAX(answered_at), MAX(csat) FROM prj_survey GROUP BY O")},
        'needs': {r[0] for r in conn.execute("SELECT O FROM prj_needs")},
        'qc': {r[0]: r[1] for r in conn.execute("SELECT O, signs_json FROM prj_qc")},
    }
    out = []
    for p in ps:
        flags, dep = _status_of(conn, p, cl, extra)
        c = cl.get(p['O'], {'n': 0, 'done': 0, 'late': 0})
        signs = json.loads(extra['qc'].get(p['O']) or '{}')
        out.append({'O': p['O'], 'B': p['B'], 'client': p['client'], 'tier': p['tier'] or '', 'title': p['title'], 'date': p['date'],
                    'confirmed': bool(p['confirmed']), 'status': p['status'], 'venue': p['venue_name'],
                    'checklist': c, 'deposit': dep, 'needs': p['O'] in extra['needs'],
                    'qc': len([s for s in signs.values() if s]) >= len(SIGNERS), 'closed': p['O'] in extra['closed'],
                    'survey': bool(extra['survey'].get(p['O'], (None,))[0]), 'flags': flags})
    out.sort(key=lambda x: (x['date'] or '9') if scope != 'closing' else '', reverse=(scope == 'closing'))
    if scope != 'closing':
        out.sort(key=lambda x: (0 if x['date'] >= t else 1, x['date'] if x['date'] >= t else ''.join(chr(255 - ord(ch)) for ch in x['date'])))
    return out


def get_project(conn, O):
    ps = _projects(conn, "AND e.operation_order=?", (O,))
    if not ps:
        raise ValueError('المشروع غير موجود')
    p = ps[0]
    if p['date'] and p['status'] != 'cancelled' and ensure_checklist(conn, O, p['date']):
        conn.commit()
    rows = lambda sql: [dict(r) for r in conn.execute(sql, (O,)).fetchall()]
    needs = conn.execute("SELECT data_json, client_ok, by_name, at FROM prj_needs WHERE O=?", (O,)).fetchone()
    qc = conn.execute("SELECT gates_json, items_json, signs_json, updated FROM prj_qc WHERE O=?", (O,)).fetchone()
    close = conn.execute("SELECT * FROM prj_close WHERE O=?", (O,)).fetchone()
    cost = conn.execute("""SELECT k, COALESCE(SUM(CASE WHEN COALESCE(net,0)<>0 THEN net ELSE COALESCE(total,0)-COALESCE(vat,0) END),0)
                           FROM exp_invoices WHERE operation_order=? AND COALESCE(is_test,0)=0 AND COALESCE(status,'active')<>'deleted'
                           GROUP BY k""", (O,)).fetchall() if conn.execute("SELECT 1 FROM sqlite_master WHERE name='exp_invoices'").fetchone() else []
    surveys = rows("SELECT token, created_at, created_by, answered_at, csat, nps, data_json FROM prj_survey WHERE O=? ORDER BY created_at DESC")
    for s in surveys:
        s['data'] = json.loads(s.pop('data_json') or '{}')
    dep = deposit_info(conn, O=O, Q=p['Q'] or None)
    p['deposit'] = dep
    return {
        'p': p, 'tiers': TIERS,
        'needs': {'fields': NEEDS_FIELDS, 'data': json.loads(needs[0] or '{}') if needs else {}, 'clientOk': needs[1] if needs else '',
                  'by': needs[2] if needs else '', 'at': needs[3] if needs else ''},
        'checklist': rows("SELECT * FROM prj_checklist WHERE O=? ORDER BY n, id"),
        'secs': [s for s, _, _ in CHECKLIST] + ['بنود إضافية'],
        'risks': rows("SELECT * FROM prj_risks WHERE O=? ORDER BY id"),
        'qc': {'gates': GATES, 'items': QC_ITEMS, 'signers': SIGNERS,
               'g': json.loads(qc[0] or '{}') if qc else {}, 'i': json.loads(qc[1] or '{}') if qc else {},
               's': json.loads(qc[2] or '{}') if qc else {}, 'updated': qc[3] if qc else ''},
        'changes': rows("SELECT * FROM prj_changes WHERE O=? ORDER BY id DESC"),
        'issues': rows("SELECT * FROM prj_issues WHERE O=? ORDER BY id DESC"),
        'damages': rows("SELECT * FROM prj_damages WHERE O=? ORDER BY id"),
        'close': dict(close) if close else None,
        'report': close_report(conn, O, p, {r[0]: r2(r[1]) for r in cost}),
        'surveys': surveys,
        'levels': [{'level': l, 'max': m if m < 1e8 else None, 'approver': a} for l, m, a in CHANGE_LEVELS],
        'issueTypes': ISSUE_TYPES, 'severity': list(SEVERITY.keys()),
    }


def close_report(conn, O, p, cost_by_k):
    rev = r2(float(p['total_price'] or 0) / 1.15)
    cost = r2(sum(cost_by_k.values()))
    dmg = conn.execute("SELECT COUNT(*), COALESCE(SUM(cost),0) FROM prj_damages WHERE O=?", (O,)).fetchone()
    sv = conn.execute("SELECT csat, nps FROM prj_survey WHERE O=? AND answered_at IS NOT NULL ORDER BY answered_at DESC LIMIT 1", (O,)).fetchone()
    cl = conn.execute("SELECT COUNT(*), SUM(status='done') FROM prj_checklist WHERE O=?", (O,)).fetchone()
    iss = conn.execute("SELECT COUNT(*), SUM(type='شكوى عميل') FROM prj_issues WHERE O=?", (O,)).fetchone()
    ch = conn.execute("SELECT COUNT(*), COALESCE(SUM(CASE WHEN status='معتمد' THEN amount ELSE 0 END),0) FROM prj_changes WHERE O=?", (O,)).fetchone()
    lab = {'sup': 'الإشراف', 'hos': 'الضيافة', 'exe': 'التنفيذ', 'pur': 'المشتريات'}
    return {
        'revenue': rev, 'revenueVat': r2(p['total_price']), 'collected': r2(p['paid_amount']),
        'remaining': r2(max(0, float(p['total_price'] or 0) - float(p['paid_amount'] or 0))),
        'cost': cost, 'costBy': {lab.get(k, k): v for k, v in cost_by_k.items()}, 'profit': r2(rev - cost),
        'margin': round((rev - cost) / rev * 100, 1) if rev else None, 'minMargin': setting(conn, 'min_margin'),
        'damages': dmg[0], 'damagesCost': r2(dmg[1]), 'csat': sv[0] if sv else None, 'nps': sv[1] if sv else None,
        'checklist': f"{cl[1] or 0}/{cl[0]}", 'issues': iss[0], 'complaints': iss[1] or 0, 'changes': ch[0], 'changesAmount': r2(ch[1]),
    }


# ───────────────────────── المؤشرات ─────────────────────────
def kpis(conn, days=90):
    t = today()
    lo = add_d(t, -days)
    ps = [p for p in _projects(conn, "AND e.status='completed'") if p['date'] and lo <= p['date'] <= t]
    Os = {p['O'] for p in ps}
    rev = sum(float(p['total_price'] or 0) / 1.15 for p in ps)
    prof = sum(float(p['profit'] or 0) for p in ps)
    vat_total = sum(float(p['total_price'] or 0) for p in ps)
    paid = sum(min(float(p['paid_amount'] or 0), float(p['total_price'] or 0)) for p in ps)
    sv = [r for r in conn.execute("SELECT O, csat, nps FROM prj_survey WHERE answered_at IS NOT NULL").fetchall() if r[0] in Os]
    cs = [r[1] for r in sv if r[1] is not None]
    nps = [r[2] for r in sv if r[2] is not None]
    comp = {r[0] for r in conn.execute("SELECT DISTINCT O FROM prj_issues WHERE type='شكوى عميل'")} & Os
    closes = {r[0]: r[1] for r in conn.execute("SELECT O, closed_at FROM prj_close WHERE closed_at IS NOT NULL")}
    on_time = 0
    for p in ps:
        ca = closes.get(p['O'])
        if ca and ca[:10] <= add_d(p['date'], 2):
            on_time += 1
    cl = conn.execute("SELECT COUNT(*), SUM(status='done') FROM prj_checklist WHERE due<>'' AND due<?", (t,)).fetchone()
    dmg = conn.execute("SELECT COUNT(*), COALESCE(SUM(cost),0) FROM prj_damages WHERE at>=?", (lo,)).fetchone()
    n = len(ps)

    def k(key, label, val, target, better='high', unit='%', note=''):
        ok = None if val is None else (val >= target if better == 'high' else val <= target)
        return {'key': key, 'label': label, 'value': val, 'target': target, 'better': better, 'unit': unit, 'ok': ok, 'note': note}
    return {'days': days, 'events': n, 'items': [
        k('csat', 'رضا العملاء', round(sum(cs) / len(cs) / 5 * 100, 1) if cs else None, 95,
          note=f"{len(cs)} استبيان من {n} مناسبة"),
        k('nps', 'مؤشر التوصية NPS', round((sum(1 for x in nps if x >= 9) - sum(1 for x in nps if x <= 6)) / len(nps) * 100) if nps else None, 70, unit=''),
        k('margin', 'هامش الربح', round(prof / rev * 100, 1) if rev else None, setting(conn, 'min_margin'), note='قبل الضريبة بعد كل المصاريف'),
        k('complaints', 'نسبة المناسبات بشكوى', round(len(comp) / n * 100, 1) if n else None, 5, better='low'),
        k('close48', 'الإقفال خلال 48 ساعة', round(on_time / n * 100, 1) if n else None, 100, note=f"{on_time} من {n}"),
        k('collection', 'نسبة التحصيل', round(paid / vat_total * 100, 1) if vat_total else None, 95),
        k('checklist', 'الالتزام بمواعيد القائمة الشاملة', round((cl[1] or 0) / cl[0] * 100, 1) if cl[0] else None, 100),
        k('response', 'نسبة الرد على الاستبيان', round(len(sv) / n * 100, 1) if n else None, 80),
    ], 'damages': {'count': dmg[0], 'cost': r2(dmg[1])}}


# ───────────────────────── الصلاحيات ─────────────────────────
def me(conn, ctx):
    u = ctx['user']
    name = (u.get('full_name') or u['username']).split(' — ')[0].strip()
    is_super = bool(ctx['perms'].get('is_super'))
    manage, depts = is_super, []
    try:
        import ops_native
        m = ops_native.member(conn, u, is_super)
        manage = manage or m['isOps']
        depts = m['depts']
    except Exception:
        pass
    import access_control as ac
    roles = ac.user_roles(u)
    if any(r in ('owner', 'general_manager', 'admin', 'project_manager', 'customer_service', 'sales') for r in roles):
        manage = True
    fin = is_super or any(r in ('owner', 'general_manager', 'finance', 'admin') for r in roles)
    return {'name': name, 'manage': manage, 'finance': fin, 'super': is_super, 'depts': depts}


def _need(m, what='manage'):
    if not m.get(what):
        raise PermissionError('هذا الإجراء لإدارة العمليات ومدير المشروع والإدارة')


def change_level(pct, kind):
    if kind in ('تغيير التاريخ', 'تغيير الموقع', 'إلغاء'):
        return CHANGE_LEVELS[3]
    for lvl in CHANGE_LEVELS:
        if pct <= lvl[1] + 1e-9:
            return lvl
    return CHANGE_LEVELS[3]


def call(conn, ctx, fn, a):
    m = me(conn, ctx)
    O = t_(a.get('O'))
    if fn == 'list':
        return {'me': m, 'items': list_projects(conn, a.get('scope') or 'active'), 'settings': {k: setting(conn, k) for k in DEFAULTS}}
    if fn == 'get':
        d = get_project(conn, O)
        d['me'] = m
        if not m['finance']:
            d['report'] = {k: v for k, v in d['report'].items() if k not in ('revenue', 'revenueVat', 'cost', 'costBy', 'profit', 'margin', 'collected', 'remaining')}
        return d
    if fn == 'kpis':
        _need(m)
        return kpis(conn, int(a.get('days') or 90))
    if fn == 'settings':
        if not m['super']:
            raise PermissionError('للإدارة فقط')
        for k in DEFAULTS:
            if k in a:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", ('prj_' + k, str(float(a[k]))))
        conn.commit()
        return {k: setting(conn, k) for k in DEFAULTS}
    if not O:
        raise ValueError('رقم أمر التشغيل مطلوب')
    if fn == 'tier':
        _need(m)
        tier = t_(a.get('tier'))
        if tier and tier not in TIERS:
            raise ValueError('تصنيف غير صالح')
        conn.execute("UPDATE customers SET tier=? WHERE id=(SELECT customer_id FROM events WHERE operation_order=?)", (tier or None, O))
    elif fn == 'needs':
        data = a.get('data') or {}
        conn.execute("INSERT OR REPLACE INTO prj_needs (O, data_json, client_ok, by_name, at) VALUES (?,?,?,?,?)",
                     (O, json.dumps(data, ensure_ascii=False), t_(a.get('clientOk')), m['name'], now()))
    elif fn == 'check':
        r = conn.execute("SELECT owner, status FROM prj_checklist WHERE id=? AND O=?", (int(a['id']), O)).fetchone()
        if not r:
            raise ValueError('البند غير موجود')
        if not m['manage'] and r[0] not in m['depts'] and not any(d in r[0] for d in m['depts']):
            raise PermissionError('هذا البند لقسم ' + r[0])
        st = a.get('status') or ('done' if r[1] != 'done' else 'todo')
        if st not in ('todo', 'doing', 'done', 'na'):
            raise ValueError('حالة غير صالحة')
        conn.execute("""UPDATE prj_checklist SET status=?, done_at=?, done_by=?, evidence=COALESCE(?, evidence), note=COALESCE(?, note)
                        WHERE id=?""", (st, now() if st in ('done', 'na') else None, m['name'] if st in ('done', 'na') else None,
                                        a.get('evidence'), a.get('note'), int(a['id'])))
    elif fn == 'checkAdd':
        _need(m)
        mx = conn.execute("SELECT COALESCE(MAX(n),0) FROM prj_checklist WHERE O=?", (O,)).fetchone()[0]
        conn.execute("INSERT INTO prj_checklist (O, sec, n, title, owner, due, custom) VALUES (?,?,?,?,?,?,1)",
                     (O, 'بنود إضافية', mx + 1, t_(a.get('title')), t_(a.get('owner')) or 'العمليات', t_(a.get('due'))))
    elif fn == 'risk':
        _need(m)
        if a.get('id'):
            if a.get('delete'):
                conn.execute("DELETE FROM prj_risks WHERE id=? AND O=?", (int(a['id']), O))
            else:
                conn.execute("UPDATE prj_risks SET risk=?, prob=?, impact=?, response=?, owner=?, status=? WHERE id=? AND O=?",
                             (t_(a.get('risk')), t_(a.get('prob')), t_(a.get('impact')), t_(a.get('response')), t_(a.get('owner')),
                              t_(a.get('status')) or 'مفتوحة', int(a['id']), O))
        else:
            conn.execute("INSERT INTO prj_risks (O, risk, prob, impact, response, owner, by_name, at) VALUES (?,?,?,?,?,?,?,?)",
                         (O, t_(a.get('risk')), t_(a.get('prob')) or 'متوسطة', t_(a.get('impact')) or 'متوسط', t_(a.get('response')),
                          t_(a.get('owner')), m['name'], now()))
    elif fn == 'qc':
        r = conn.execute("SELECT gates_json, items_json, signs_json FROM prj_qc WHERE O=?", (O,)).fetchone()
        g, i, s = [json.loads(x or '{}') for x in (r or ('{}', '{}', '{}'))]
        if a.get('gate') in GATES:
            _need(m)
            g[a['gate']] = None if g.get(a['gate']) else {'by': m['name'], 'at': now()}
        if a.get('item') in QC_ITEMS:
            i[a['item']] = {'v': a.get('v'), 'note': t_(a.get('note')), 'by': m['name'], 'at': now()}
        if a.get('sign') in SIGNERS:
            _need(m)
            if not s.get(a['sign']):
                bad = [k for k in QC_ITEMS if (i.get(k) or {}).get('v') != 'ok']
                if bad:
                    raise ValueError(f'ما ينفع الاعتماد: {len(bad)} بند فحص غير مطابق أو لم يُفحص')
                s[a['sign']] = {'by': m['name'], 'at': now()}
            else:
                s[a['sign']] = None
        conn.execute("INSERT OR REPLACE INTO prj_qc (O, gates_json, items_json, signs_json, updated) VALUES (?,?,?,?,?)",
                     (O, json.dumps(g, ensure_ascii=False), json.dumps(i, ensure_ascii=False), json.dumps(s, ensure_ascii=False), now()))
    elif fn == 'change':
        if a.get('id') and a.get('decision'):
            row = conn.execute("SELECT level, approver, status FROM prj_changes WHERE id=? AND O=?", (int(a['id']), O)).fetchone()
            if not row:
                raise ValueError('الطلب غير موجود')
            if row[0] in ('جوهري', 'جذري') and not (m['super'] or m['finance']):
                raise PermissionError(f'اعتماد التغيير {row[0]} لـ{row[1]}')
            _need(m)
            dec = a['decision'] if a['decision'] in ('معتمد', 'مرفوض', 'منفّذ') else 'معتمد'
            conn.execute("UPDATE prj_changes SET status=?, decided_by=?, decided_at=? WHERE id=?", (dec, m['name'], now(), int(a['id'])))
        else:
            e = conn.execute("SELECT total_price FROM events WHERE operation_order=?", (O,)).fetchone()
            base = float(e[0] or 0) if e else 0
            amt = float(a.get('amount') or 0)
            pct = round(abs(amt) / base * 100, 1) if base else 0
            lvl, _, appr = change_level(pct if amt else 0, t_(a.get('kind')))
            conn.execute("""INSERT INTO prj_changes (O, descr, kind, amount, pct, level, approver, by_name, at) VALUES (?,?,?,?,?,?,?,?,?)""",
                         (O, t_(a.get('descr')), t_(a.get('kind')) or 'تعديل بند', amt, pct, lvl, appr, m['name'], now()))
    elif fn == 'issue':
        if a.get('id'):
            iid = int(a['id'])
            if a.get('ack'):
                conn.execute("UPDATE prj_issues SET ack_at=COALESCE(ack_at, ?), status=CASE WHEN status='مفتوحة' THEN 'قيد المعالجة' ELSE status END WHERE id=?", (now(), iid))
            if a.get('resolve'):
                conn.execute("UPDATE prj_issues SET status='محلولة', resolved_at=?, resolution=?, ack_at=COALESCE(ack_at, ?) WHERE id=?",
                             (now(), t_(a.get('resolution')), now(), iid))
            if a.get('escalate'):
                order = list(SEVERITY.keys())
                cur = conn.execute("SELECT severity FROM prj_issues WHERE id=?", (iid,)).fetchone()[0]
                nxt = order[min(len(order) - 1, order.index(cur) + 1)] if cur in order else 'عالية'
                conn.execute("UPDATE prj_issues SET severity=?, type=CASE WHEN type='مشكلة تشغيلية' THEN 'تصعيد' ELSE type END WHERE id=?", (nxt, iid))
        else:
            sev = t_(a.get('severity')) if t_(a.get('severity')) in SEVERITY else 'متوسطة'
            conn.execute("INSERT INTO prj_issues (O, type, severity, descr, owner, by_name, at) VALUES (?,?,?,?,?,?,?)",
                         (O, t_(a.get('type')) if t_(a.get('type')) in ISSUE_TYPES else 'مشكلة تشغيلية', sev, t_(a.get('descr')),
                          t_(a.get('owner')), m['name'], now()))
    elif fn == 'damage':
        if a.get('delete'):
            _need(m)
            conn.execute("DELETE FROM prj_damages WHERE id=? AND O=?", (int(a['id']), O))
        else:
            conn.execute("INSERT INTO prj_damages (O, item, qty, cause, cost, action, by_name, at) VALUES (?,?,?,?,?,?,?,?)",
                         (O, t_(a.get('item')), float(a.get('qty') or 1), t_(a.get('cause')), float(a.get('cost') or 0),
                          t_(a.get('action')) or 'صيانة', m['name'], now()))
    elif fn == 'close':
        _need(m)
        if a.get('reopen'):
            conn.execute("UPDATE prj_close SET closed_at=NULL, closed_by=NULL WHERE O=?", (O,))
        else:
            d = get_project(conn, O)
            open_iss = [x for x in d['issues'] if x['status'] != 'محلولة']
            if a.get('final') and open_iss:
                raise ValueError(f'فيه {len(open_iss)} شكوى/مشكلة مفتوحة — تُحل قبل الإقفال')
            conn.execute("""INSERT INTO prj_close (O, lessons, team_eval, report_json, closed_by, closed_at) VALUES (?,?,?,?,?,?)
                            ON CONFLICT(O) DO UPDATE SET lessons=excluded.lessons, team_eval=excluded.team_eval, report_json=excluded.report_json,
                            closed_by=COALESCE(excluded.closed_by, prj_close.closed_by), closed_at=COALESCE(excluded.closed_at, prj_close.closed_at)""",
                         (O, t_(a.get('lessons')), t_(a.get('teamEval')), json.dumps(d['report'], ensure_ascii=False),
                          m['name'] if a.get('final') else None, now() if a.get('final') else None))
            if a.get('final'):
                conn.execute("""UPDATE prj_checklist SET status='done', done_at=?, done_by=? WHERE O=? AND status<>'done'
                                AND title IN ('إعداد تقرير إغلاق المشروع','إغلاق ملف المشروع في المنصة')""", (now(), m['name'], O))
    elif fn == 'survey':
        tok = secrets.token_urlsafe(9)
        conn.execute("INSERT INTO prj_survey (token, O, created_at, created_by) VALUES (?,?,?,?)", (tok, O, now(), m['name']))
        conn.execute("""UPDATE prj_checklist SET status='done', done_at=?, done_by=? WHERE O=? AND title='إرسال استبيان رضا العميل' AND status<>'done'""",
                     (now(), m['name'], O))
        conn.commit()
        return {'token': tok, 'url': '/survey/' + tok}
    else:
        raise ValueError('إجراء غير معروف: ' + fn)
    conn.commit()
    return call(conn, ctx, 'get', {'O': O})


# ───────────────────────── الاستبيان العام ─────────────────────────
SURVEY_Q = {
    'csat': 'ما مدى رضاك العام عن تجربتك مع أبيلا؟ (1–5)',
    'nps': 'ما احتمالية أن توصي بأبيلا لصديقة أو قريبة؟ (0–10)',
    'expect': ['تجاوزت توقعاتي بكثير', 'كانت كما توقعت تماماً', 'قريبة من توقعاتي', 'أقل من توقعاتي'],
    'comm': 'التواصل قبل المناسبة (1–5)', 'exec': 'التنفيذ يوم المناسبة (1–5)', 'time': 'الالتزام بالمواعيد (1–5)',
    'guests': ['ردود استثنائية ومذهلة', 'ردود إيجابية كثيرة', 'تعليقات إيجابية متفرقة', 'ردود محايدة', 'كانت هناك ملاحظات سلبية'],
    'again': ['نعم بالتأكيد', 'نعم عند المناسبة القادمة', 'ربما', 'لا حالياً'],
    'photos': ['نعم بإظهار وجوه الضيوف', 'نعم مع إخفاء الوجوه', 'نعم دون ذكر اسمي', 'لا، أفضّل عدم النشر'],
}


def survey_public(conn, method, tok, data):
    r = conn.execute("""SELECT s.token, s.O, s.answered_at, e.title, COALESCE(e.actual_date, e.event_date) d
                        FROM prj_survey s LEFT JOIN events e ON e.operation_order=s.O WHERE s.token=?""", (tok,)).fetchone()
    if not r:
        return 404, {'error': 'الرابط غير صحيح'}
    if method == 'GET':
        return 200, {'title': r[3], 'date': r[4], 'answered': bool(r[2]), 'q': SURVEY_Q}
    if r[2]:
        return 200, {'ok': True, 'already': True}
    try:
        csat = int(data.get('csat'))
        nps = int(data.get('nps'))
        assert 1 <= csat <= 5 and 0 <= nps <= 10
    except Exception:
        return 400, {'error': 'أكملي تقييم الرضا والتوصية'}
    clean = {k: (str(v)[:2000] if not isinstance(v, (int, float)) else v) for k, v in (data or {}).items() if k in
             ('csat', 'nps', 'expect', 'comm', 'exec', 'time', 'best', 'surprise', 'better', 'guests', 'again', 'photos', 'ref_name', 'ref_phone', 'comment')}
    conn.execute("UPDATE prj_survey SET answered_at=?, data_json=?, csat=?, nps=? WHERE token=?",
                 (now(), json.dumps(clean, ensure_ascii=False), csat, nps, tok))
    if csat <= 3 or nps <= 6:   # عميل غير راضٍ → شكوى تلقائية للمتابعة
        conn.execute("INSERT INTO prj_issues (O, type, severity, descr, owner, by_name, at) VALUES (?,?,?,?,?,?,?)",
                     (r[1], 'شكوى عميل', 'عالية' if csat <= 2 else 'متوسطة',
                      f"تقييم منخفض في الاستبيان (رضا {csat}/5 · توصية {nps}/10): {clean.get('better') or clean.get('comment') or ''}".strip(),
                      'خدمة العملاء', 'الاستبيان', now()))
    conn.commit()
    return 200, {'ok': True}


def handle(h, conn, method, path, query, data, ctx, send_json):
    m = re.match(r'^/api/public/survey/([\w-]+)$', path)
    if m:
        init_tables(conn)
        st, body = survey_public(conn, method, m[1], data or {})
        send_json(body, st)
        return True
    if not path.startswith('/api/prj/') or not ctx:
        return False
    try:
        init_tables(conn)
        if path == '/api/prj/call' and method == 'POST':
            send_json({'ok': True, 'data': call(conn, ctx, (data or {}).get('fn'), (data or {}).get('args') or {})})
            return True
        if path == '/api/prj/deposit' and method == 'GET':
            q = (query.get('q') or [''])[0]
            send_json(deposit_ok(conn, q))
            return True
    except PermissionError as e:
        send_json({'ok': False, 'error': str(e)}, 403)
        return True
    except (ValueError, KeyError) as e:
        send_json({'ok': False, 'error': str(e)})
        return True
    return False
