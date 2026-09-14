import type { Lang } from "./api/types";

/** Interface copy. Answers come back in the asker's language from the engine;
 *  this is only the chrome around them.
 *
 *  Error copy says what happened and what to do next (PDD §9). No string here
 *  says only that something went wrong. */
export interface Copy {
  readonly appName: string;
  readonly role: string;
  readonly language: string;
  readonly askPlaceholder: string;
  readonly ask: string;
  readonly emptyTitle: string;
  readonly emptyBody: string;
  readonly recordedNote: string;
  readonly startWithExample: string;
  readonly thinking: string;
  readonly chart: string;
  readonly table: string;
  readonly askWhy: string;
  readonly askWhyCut: string;
  readonly receipt: string;
  readonly noReceipt: string;
  readonly noReceiptBody: string;
  readonly showSql: string;
  readonly catalog: string;
  readonly catalogTitle: string;
  readonly catalogBlurb: string;
  readonly catalogRunOne: string;
  readonly takeTour: string;
  readonly tourNext: string;
  readonly tourSkip: string;
  readonly tourDone: string;
  readonly tourStepOf: (n: number, total: number) => string;
  readonly tour: readonly { readonly title: string; readonly body: string }[];
  readonly tabMetrics: string;
  readonly tabSchema: string;
  readonly schemaBlurb: string;
  readonly ownedBy: string;
  readonly breakDownBy: string;
  readonly joinPath: string;
  readonly primaryKey: string;
  readonly referenceTable: string;
  readonly definedIn: string;
  readonly exampleAnswerLabel: string;
  readonly traceIdle: string;
  readonly closeLabel: string;
  readonly metric: string;
  readonly window: string;
  readonly scope: string;
  readonly fresh: string;
  readonly source: string;
  readonly excludes: string;
  readonly defaults: string;
  readonly siblings: string;
  readonly more: string;
  readonly less: string;
  readonly copied: string;
  readonly plan: string;
  readonly sql: string;
  readonly trace: string;
  readonly answerRegion: string;
  readonly statusOf: (status: string) => string;
  readonly rows: (count: number) => string;
  readonly truncated: string;
  readonly roleNames: Readonly<Record<string, string>>;
  readonly errors: Readonly<Record<string, string>>;
  readonly errorFallback: string;
  readonly retryIn: (seconds: number) => string;
  readonly catalogModeTitle: string;
  readonly catalogModeBody: string;
  readonly runIt: string;
  readonly noMetricChosen: string;
}

const EN: Copy = {
  appName: "Receipts",
  role: "Role",
  language: "Language",
  askPlaceholder: "Ask about payments…",
  ask: "Ask",
  emptyTitle: "Ask a question about payments.",
  emptyBody: "Every answer comes with a receipt saying where the number came from.",
  recordedNote:
    "Answers here are replayed from the recorded evaluation, so they are exactly the ones that were measured.",
  startWithExample: "Start with an example below.",
  thinking: "Working",
  chart: "Chart",
  table: "Table",
  askWhy: "Ask why",
  askWhyCut: "Contribution analysis is not built (PDD §13 cut).",
  receipt: "Receipt",
  noReceipt: "No receipt",
  noReceiptBody: "Nothing ran against the data, so there is nothing to show a receipt for.",
  showSql: "Show SQL, plan and trace",
  catalog: "Catalog",
  catalogTitle: "Governed metrics",
  catalogBlurb:
    "Every metric a question can reach. Each one is defined in the glossary, and a role only sees the ones its capabilities allow.",
  catalogRunOne: "Run one",
  takeTour: "Take the tour",
  tourNext: "Next",
  tourSkip: "Skip",
  tourDone: "Done",
  tourStepOf: (n, total) => `${n} of ${total}`,
  tour: [
    {
      title: "The answer",
      body: "Ask in plain language — English, Tamil, Hindi or Tanglish. The answer comes back in the language you asked in.",
    },
    {
      title: "The receipt",
      body:
        "This is the point of the project. Every answer carries one: which metric was used and how it is defined, the window, the scope it was computed over, what was excluded, and every default that was applied — including the reporting currency. If a number is wrong, the receipt is where you find out why, without reading any code.",
    },
    {
      title: "The status",
      body: "VERIFIED, UNVERIFIED, CLARIFY, ABSTAIN or DENIED. The system says which it is instead of always answering.",
    },
    {
      title: "How it was answered",
      body: "The stages appear here as your question runs. The model produces a typed plan; a deterministic compiler writes the SQL.",
    },
    {
      title: "The governed layer",
      body: "Every metric a question can reach, with its definition and the team that owns it, scoped to your role. The Schema tab beneath shows the tables underneath — those are columns, these are definitions.",
    },
    {
      title: "Change role",
      body: "Ask the same question as another role and it is scoped differently, or refused outright. Scope is compiled into the SQL, not requested in a prompt.",
    },
    {
      title: "Change language",
      body: "English, Tamil, Hindi and hand-written Tanglish. Each has its own example questions.",
    },
  ],
  tabMetrics: "Governed metrics",
  tabSchema: "Schema",
  schemaBlurb:
    "The underlying tables — not the governed layer. These are columns; the metrics beside them are definitions with an owner, an exclusion list and a glossary reference. The difference is the point.",
  ownedBy: "Owned by",
  breakDownBy: "Break down by",
  joinPath: "Scope join",
  primaryKey: "Key",
  referenceTable: "reference",
  definedIn: "Defined in",
  exampleAnswerLabel: "An example, answered when this page loaded",
  traceIdle: "The stages will appear here as your question runs.",
  closeLabel: "Close",
  metric: "Metric",
  window: "Window",
  scope: "Scope",
  fresh: "Fresh",
  source: "Source",
  excludes: "Excludes",
  defaults: "Defaults applied",
  siblings: "Related metrics",
  more: "more",
  less: "less",
  copied: "Copied",
  plan: "Plan",
  sql: "SQL",
  trace: "Steps",
  answerRegion: "Answer",
  statusOf: (status) => `status: ${status.toLowerCase()}`,
  rows: (count) => `${count} row${count === 1 ? "" : "s"}`,
  truncated: "Showing the first rows only.",
  roleNames: {
    rm_tamil_nadu: "Chennai regional manager",
    global_finance: "Global finance",
    store_ops_uk: "UK store ops",
    admin: "Admin",
  },
  errors: {
    MODEL_UNAVAILABLE:
      "Nothing is broken — this question just was not part of the recorded evaluation, so there is no recorded answer to replay. The examples below are, and every one of them works. You can also open the catalog to run any metric directly, with no model involved at all.",
    RATE_LIMITED: "That is more questions than the demo allows in a minute.",
    DB_TIMEOUT: "The warehouse took too long. Ask again, or narrow the window.",
    DB_UNAVAILABLE: "The warehouse is not answering. Nothing was run.",
    FORBIDDEN: "This role cannot see that. Switch role in the header to compare.",
    AUTH_REQUIRED: "The demo session expired. Pick a role again in the header.",
    BUDGET_EXCEEDED: "This question ran out of its token budget. Try a shorter one.",
    VALIDATION_FAILED: "The plan did not pass validation, so nothing was run.",
    GUARD_REJECTED: "The query was refused by the safety guard. Nothing was run.",
    BRIDGE_UNAVAILABLE:
      "Live gateway queries are not part of this build (PDD §13 cut). Nothing was run.",
    NOT_FOUND: "There is nothing here to show.",
  },
  errorFallback: "The request did not complete, and nothing was run. Try again.",
  retryIn: (seconds) => `Try again in ${seconds}s.`,
  catalogModeTitle: "Catalog mode",
  catalogModeBody:
    "The model is unavailable. Saved metrics still run, with the same scope and the same receipt.",
  runIt: "Run",
  noMetricChosen: "Pick a metric to run.",
};

const TA: Copy = {
  ...EN,
  role: "பங்கு",
  language: "மொழி",
  askPlaceholder: "Payments பற்றி கேளுங்கள்…",
  ask: "கேள்",
  emptyTitle: "Payments பற்றி ஒரு கேள்வி கேளுங்கள்.",
  emptyBody: "ஒவ்வொரு பதிலுடனும், அந்த எண் எங்கிருந்து வந்தது என்று சொல்லும் ஒரு receipt வரும்.",
  recordedNote:
    "இங்குள்ள பதில்கள் பதிவு செய்யப்பட்ட மதிப்பீட்டிலிருந்து replay செய்யப்படுகின்றன — அளவிடப்பட்ட அதே பதில்கள்.",
  startWithExample: "கீழே உள்ள எடுத்துக்காட்டு ஒன்றில் தொடங்குங்கள்.",
  thinking: "வேலை நடக்கிறது",
  chart: "விளக்கப்படம்",
  table: "அட்டவணை",
  askWhy: "ஏன் என்று கேள்",
  receipt: "Receipt",
  noReceipt: "Receipt இல்லை",
  noReceiptBody: "தரவுக்கு எதிராக எதுவும் இயக்கப்படவில்லை, எனவே காட்ட receipt எதுவும் இல்லை.",
  showSql: "SQL, plan மற்றும் steps காட்டு",
  catalog: "Catalog",
  catalogTitle: "ஆளுகை செய்யப்பட்ட metrics",
  catalogBlurb:
    "ஒரு கேள்வி அணுகக்கூடிய ஒவ்வொரு metric-ம். ஒவ்வொன்றும் glossary-யில் வரையறுக்கப்பட்டுள்ளது; ஒரு பங்கு அதன் அனுமதிகள் இடும் metrics-ஐ மட்டுமே காணும்.",
  catalogRunOne: "ஒன்றை இயக்கு",
  takeTour: "சுற்றுப்பயணம்",
  tourNext: "அடுத்து",
  tourSkip: "தவிர்",
  tourDone: "முடிந்தது",
  tourStepOf: (n, total) => `${total}-ல் ${n}`,
  tour: [
    {
      title: "பதில்",
      body: "எளிய மொழியில் கேளுங்கள் — ஆங்கிலம், தமிழ், இந்தி அல்லது Tanglish. நீங்கள் கேட்ட மொழியிலேயே பதில் வரும்.",
    },
    {
      title: "Receipt",
      body:
        "இதுதான் இந்தத் திட்டத்தின் மையம். ஒவ்வொரு பதிலுடனும் ஒன்று வரும்: எந்த metric, அதன் வரையறை, காலம், எல்லை, விலக்கப்பட்டவை, மற்றும் பயன்படுத்தப்பட்ட ஒவ்வொரு இயல்புநிலையும் — reporting currency உட்பட. ஒரு எண் தவறாக இருந்தால், code படிக்காமலேயே காரணத்தை receipt-ல் காணலாம்.",
    },
    {
      title: "நிலை",
      body: "VERIFIED, UNVERIFIED, CLARIFY, ABSTAIN அல்லது DENIED. எப்போதும் பதிலளிப்பதற்குப் பதிலாக, எது என்பதை அமைப்பு சொல்கிறது.",
    },
    {
      title: "எப்படி பதிலளிக்கப்பட்டது",
      body: "உங்கள் கேள்வி இயங்கும்போது படிகள் இங்கே தோன்றும். Model ஒரு typed plan-ஐ உருவாக்குகிறது; ஒரு deterministic compiler SQL-ஐ எழுதுகிறது.",
    },
    {
      title: "ஆளுகை அடுக்கு",
      body: "ஒரு கேள்வி அணுகக்கூடிய ஒவ்வொரு metric-ம், அதன் வரையறை மற்றும் உரிமையாளர் குழுவுடன், உங்கள் பங்குக்கு ஏற்ப. கீழே உள்ள Schema tab அடிப்படை tables-ஐக் காட்டுகிறது.",
    },
    {
      title: "பங்கை மாற்று",
      body: "அதே கேள்வியை வேறு பங்காகக் கேட்டால் எல்லை மாறும், அல்லது மறுக்கப்படும். எல்லை SQL-ல் compile செய்யப்படுகிறது, prompt-ல் கேட்கப்படுவதில்லை.",
    },
    {
      title: "மொழியை மாற்று",
      body: "ஆங்கிலம், தமிழ், இந்தி மற்றும் கையால் எழுதப்பட்ட Tanglish. ஒவ்வொன்றுக்கும் தனி எடுத்துக்காட்டுக் கேள்விகள்.",
    },
  ],
  tabMetrics: "ஆளுகை metrics",
  tabSchema: "Schema",
  schemaBlurb:
    "அடிப்படை tables — ஆளுகை அடுக்கு அல்ல. இவை columns; அருகில் உள்ள metrics என்பவை உரிமையாளர், விலக்குப் பட்டியல் மற்றும் glossary குறிப்புடன் கூடிய வரையறைகள்.",
  ownedBy: "உரிமையாளர்",
  breakDownBy: "பிரிக்க",
  joinPath: "Scope join",
  primaryKey: "Key",
  referenceTable: "reference",
  definedIn: "வரையறை",
  exampleAnswerLabel: "இந்தப் பக்கம் ஏற்றப்பட்டபோது பதிலளிக்கப்பட்ட ஓர் எடுத்துக்காட்டு",
  traceIdle: "உங்கள் கேள்வி இயங்கும்போது படிகள் இங்கே தோன்றும்.",
  closeLabel: "மூடு",
  metric: "Metric",
  window: "காலம்",
  scope: "எல்லை",
  fresh: "புதுப்பிப்பு",
  source: "மூலம்",
  excludes: "விலக்கப்பட்டவை",
  defaults: "இயல்புநிலைகள்",
  siblings: "தொடர்புடைய metrics",
  more: "மேலும்",
  less: "குறைவாக",
  copied: "நகலெடுக்கப்பட்டது",
  plan: "Plan",
  sql: "SQL",
  trace: "படிகள்",
  answerRegion: "பதில்",
  truncated: "முதல் வரிசைகள் மட்டும் காட்டப்படுகின்றன.",
  roleNames: {
    rm_tamil_nadu: "சென்னை மண்டல மேலாளர்",
    global_finance: "உலகளாவிய நிதி",
    store_ops_uk: "UK store ops",
    admin: "Admin",
  },
  errorFallback: "கோரிக்கை முடியவில்லை, எதுவும் இயக்கப்படவில்லை. மீண்டும் முயற்சிக்கவும்.",
  catalogModeTitle: "Catalog mode",
  catalogModeBody:
    "Model கிடைக்கவில்லை. சேமிக்கப்பட்ட metrics இன்னும் இயங்கும் — அதே எல்லை, அதே receipt.",
  runIt: "இயக்கு",
};

const HI: Copy = {
  ...EN,
  role: "भूमिका",
  language: "भाषा",
  askPlaceholder: "भुगतान के बारे में पूछें…",
  ask: "पूछें",
  emptyTitle: "भुगतान के बारे में एक सवाल पूछें।",
  emptyBody: "हर जवाब के साथ एक receipt आती है जो बताती है कि यह संख्या कहाँ से आई।",
  recordedNote:
    "यहाँ के जवाब रिकॉर्ड किए गए मूल्यांकन से replay होते हैं — वही जवाब जो मापे गए थे।",
  startWithExample: "नीचे दिए किसी उदाहरण से शुरू करें।",
  thinking: "काम चल रहा है",
  chart: "चार्ट",
  table: "तालिका",
  askWhy: "क्यों पूछें",
  receipt: "Receipt",
  noReceipt: "कोई receipt नहीं",
  noReceiptBody: "डेटा पर कुछ नहीं चला, इसलिए दिखाने के लिए कोई receipt नहीं है।",
  showSql: "SQL, plan और steps दिखाएँ",
  catalog: "Catalog",
  catalogTitle: "शासित metrics",
  catalogBlurb:
    "हर वह metric जिस तक कोई सवाल पहुँच सकता है। हर एक glossary में परिभाषित है, और कोई भूमिका केवल वही देखती है जिसकी अनुमति उसके पास है।",
  catalogRunOne: "एक चलाएँ",
  takeTour: "परिचय देखें",
  tourNext: "आगे",
  tourSkip: "छोड़ें",
  tourDone: "पूरा",
  tourStepOf: (n, total) => `${total} में से ${n}`,
  tour: [
    {
      title: "जवाब",
      body: "सामान्य भाषा में पूछें — अंग्रेज़ी, तमिल, हिंदी या Tanglish। जवाब उसी भाषा में आता है जिसमें आपने पूछा।",
    },
    {
      title: "Receipt",
      body:
        "यही इस प्रोजेक्ट का मूल है। हर जवाब के साथ एक आती है: कौन-सा metric और उसकी परिभाषा, अवधि, दायरा, क्या शामिल नहीं था, और लागू हुआ हर डिफ़ॉल्ट — reporting currency सहित। अगर कोई संख्या ग़लत है, तो कोड पढ़े बिना कारण receipt में मिलेगा।",
    },
    {
      title: "स्थिति",
      body: "VERIFIED, UNVERIFIED, CLARIFY, ABSTAIN या DENIED। सिस्टम हमेशा जवाब देने के बजाय बताता है कि स्थिति क्या है।",
    },
    {
      title: "जवाब कैसे बना",
      body: "आपका सवाल चलते ही चरण यहाँ दिखेंगे। Model एक typed plan बनाता है; एक deterministic compiler SQL लिखता है।",
    },
    {
      title: "शासित परत",
      body: "हर वह metric जिस तक सवाल पहुँच सकता है, उसकी परिभाषा और स्वामी टीम के साथ, आपकी भूमिका के अनुसार। नीचे Schema tab अंतर्निहित tables दिखाता है।",
    },
    {
      title: "भूमिका बदलें",
      body: "वही सवाल दूसरी भूमिका से पूछें और दायरा बदल जाएगा, या मना कर दिया जाएगा। दायरा SQL में compile होता है, prompt में माँगा नहीं जाता।",
    },
    {
      title: "भाषा बदलें",
      body: "अंग्रेज़ी, तमिल, हिंदी और हाथ से लिखी Tanglish। हर एक के अपने उदाहरण सवाल हैं।",
    },
  ],
  tabMetrics: "शासित metrics",
  tabSchema: "Schema",
  schemaBlurb:
    "अंतर्निहित tables — शासित परत नहीं। ये columns हैं; इनके साथ के metrics परिभाषाएँ हैं, जिनका एक owner, बहिष्करण सूची और glossary संदर्भ है।",
  ownedBy: "स्वामी",
  breakDownBy: "विभाजित करें",
  joinPath: "Scope join",
  primaryKey: "Key",
  referenceTable: "reference",
  definedIn: "परिभाषा",
  exampleAnswerLabel: "इस पेज के लोड होने पर दिया गया एक उदाहरण",
  traceIdle: "आपका सवाल चलते ही चरण यहाँ दिखेंगे।",
  closeLabel: "बंद करें",
  metric: "Metric",
  window: "अवधि",
  scope: "दायरा",
  fresh: "ताज़ा",
  source: "स्रोत",
  excludes: "शामिल नहीं",
  defaults: "लागू डिफ़ॉल्ट",
  siblings: "संबंधित metrics",
  more: "और",
  less: "कम",
  copied: "कॉपी हो गया",
  plan: "Plan",
  sql: "SQL",
  trace: "चरण",
  answerRegion: "जवाब",
  truncated: "केवल पहली पंक्तियाँ दिखाई जा रही हैं।",
  roleNames: {
    rm_tamil_nadu: "चेन्नई क्षेत्रीय प्रबंधक",
    global_finance: "वैश्विक वित्त",
    store_ops_uk: "UK store ops",
    admin: "Admin",
  },
  errorFallback: "अनुरोध पूरा नहीं हुआ, और कुछ नहीं चला। दोबारा कोशिश करें।",
  catalogModeTitle: "Catalog mode",
  catalogModeBody:
    "Model उपलब्ध नहीं है। सहेजे गए metrics अब भी चलते हैं — वही दायरा, वही receipt।",
  runIt: "चलाएँ",
};

// `ta-Latn` deliberately maps to the ENGLISH chrome. Tanglish is code-mixed
// with English already, so English labels around Tanglish examples read as one
// register; Tamil-script labels around Latin-script examples read as two. There
// is no Tanglish chrome to write until someone writes it.
const COPY: Record<string, Copy> = { en: EN, ta: TA, hi: HI, "ta-Latn": EN };

export function copyFor(language: Lang | string): Copy {
  return COPY[language] ?? EN;
}

// `ta-Latn` is offered because it WORKS, not because the engine supports it:
// the nine demo examples have hand-written Tanglish forms and recordings to
// match. A toggle option with no answerable question behind it would render the
// chrome in a language and 503 on every example, which is a worse disclosure
// than no option at all.
export const UI_LANGS = ["en", "ta", "hi", "ta-Latn"] as const;
export const LANG_LABEL: Record<string, string> = {
  en: "EN",
  ta: "த",
  hi: "हि",
  // Tanglish is Tamil written in Latin script and mixed with English, so it is
  // labelled in the script it is written in.
  "ta-Latn": "Tanglish",
};
