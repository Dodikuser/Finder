import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const uk = {
  nav: { chat: "Чат", agents: "Агенти", grants: "Гранти", accounts: "Акаунти", logout: "Вийти", myAgents: "Мої агенти", newAgent: "Новий агент", theme: "Тема" },
  auth: {
    tagline: "Агенти, що шукають в інтернеті за вас: медицина, гранти, будь-яка тема.",
    login: "Увійти", register: "Створити акаунт", email: "Email", password: "Пароль", name: "Ім'я",
    toRegister: "Немає акаунта? Зареєструватися", toLogin: "Вже є акаунт? Увійти",
    passwordHint: "Мінімум 8 символів",
    invite: "Код запрошення",
    errors: { invalid_invite: "Невірний код запрошення", registration_closed: "Реєстрацію закрито", too_many_attempts: "Забагато спроб. Спробуйте за кілька хвилин.", invalid_credentials: "Невірний email або пароль", email_taken: "Цей email вже зареєстровано", invalid_email: "Некоректний email", generic: "Щось пішло не так, спробуйте ще раз" },
  },
  chat: {
    model: "Модель", placeholder: "Запитайте агента…", send: "Надіслати", stop: "Зупинити",
    newChat: "Нова розмова", history: "Розмови", working: "Агент працює", didSteps: "Що зробив агент", steps_one: "{{count}} крок", steps_few: "{{count}} кроки", steps_many: "{{count}} кроків", steps_other: "{{count}} кроку",
    emptyTitle: "З чого почнемо?", emptyHint: "Агент шукає в інтернеті, читає джерела і відповідає з посиланнями.",
    needsAccount: "Щоб агент запрацював, підключіть акаунт провайдера моделей.", connect: "Підключити акаунт",
    cancelled: "Зупинено", failed: "Помилка", thinking: "Міркує…", loadingModels: "Завантаження моделей…",
    noModels: "Немає моделей", deleteChat: "Видалити розмову", grantsSaved: "Збережено на дошці грантів: {{count}}", openBoard: "Відкрити дошку",
    blocked: "Дію заблоковано: агент не має доступу до файлів і терміналу",
    suggestions: {
      "medical-ai": ["Свіжі дослідження LLM у радіології за останні 6 місяців", "Які AI-продукти для клінічної документації зараз лідирують?", "Що EU AI Act вимагає від медичних AI-систем?"],
      "topic-researcher": ["Знайди відкриті датасети для розпізнавання медичних зображень", "Огляд AI-агентів для наукового пошуку у 2026 році"],
      "it-grants": ["Знайди відкриті гранти для університетів України у сфері AI", "Перевір гранти на ГУРТ і House of Europe для IT-факультету"],
    },
  },
  accounts: {
    crumbs: ["Налаштування", "Провайдери", "Акаунти"], title: "Підключити акаунт",
    subtitle: "Увійдіть через підписку — без копіювання API-ключа. Токени зберігаються лише у вашому профілі агента.",
    haveKey: "Маєте API-ключ?", recommended: "Рекомендовано", connected: "Підключені", other: "Інші провайдери", apiKeys: "API-ключі",
    signIn: "Увійти", disconnect: "Відключити", connectedBadge: "Підключено",
    deviceHint: "Відкриває сторінку перевірки — Finder під'єднується автоматично",
    codeHint: { claude: "Вхід на claude.ai — потім вставте сюди код, який покаже сторінка", gemini: "Вхід у Google — потім вставте сюди код. Моделі Gemini за вашим планом Antigravity", other: "Вхід на сайті провайдера — потім вставте сюди код" },
    codeStep1: "1. Відкрийте сторінку входу і увійдіть у свій акаунт.", codeStep2: "2. Підтвердьте доступ — сторінка покаже код.",
    codeStep3: "3. Скопіюйте код і вставте його нижче.", openSignIn: "Відкрити сторінку входу", codeLabel: "Код авторизації", codeSubmit: "Підключити",
    codeNote: { claude: "Працює з підпискою Claude Pro або Max. Anthropic може вимагати додаткових кредитів (extra usage) для використання підписки у сторонніх застосунках.", gemini: "Вхід виконує офіційний Antigravity CLI від Google. Сесія зберігається лише у вашому профілі на сервері; Finder не бачить токен.", other: "" },
    recommendedHint: "Одна підписка — сотні моделей, рідний провайдер Hermes",
    keyHint: "Ключ передається у ваш профіль Hermes і більше ніде не зберігається",
    modalTitle: "Вхід у {{name}}", step1: "1. Відкрийте сторінку перевірки.", step2: "2. Введіть код нижче і підтвердьте доступ.",
    open: "Відкрити сторінку перевірки", waiting: "Очікуємо підтвердження…", approved: "Готово! Акаунт підключено.",
    failed: "Не вдалося увійти", starting: "Запускаємо вхід…", copy: "Копіювати", copied: "Скопійовано",
    keyTitle: "Додати API-ключ", provider: "Провайдер", key: "API-ключ", save: "Зберегти", saving: "Перевіряємо…",
  },
  agents: {
    title: "Конструктор агента", subtitle: "Перелаштуйте агента під нову задачу або створіть копію пресету",
    duplicate: "Дублювати", save: "Зберегти агента", saved: "Збережено", name: "Назва", description: "Опис",
    instructions: "Інструкція для агента", tools: "Інструменти пошуку", skills: "Навички", sources: "Сайти-джерела",
    sourcesHint: "— по одному на рядок", orgProfile: "Профіль організації", orgHint: "— для оцінки грантів", orgTemplateWarning: "Це шаблон: замініть текст у [квадратних дужках] на дані вашої організації — інакше вердикти будуть неточні.", editProfile: "Профіль організації",
    model: "Модель за замовчуванням", modelAuto: "Як у розмові", language: "Мова відповіді", langUi: "Як в інтерфейсі",
    kind: "Тип агента", kindResearch: "Дослідник", kindGrants: "Аналітик грантів",
    isolatedTitle: "Ізольоване середовище", isolatedBody: "Агент бачить лише інтернет-інструменти. Файли, термінал і виконання коду вимкнені на рівні профілю Hermes.",
    reset: "Скинути до пресету", delete: "Видалити", confirmDelete: "Видалити агента разом з розмовами?", newAgent: "Новий агент",
    openChat: "Відкрити чат", list: "Агенти",
  },
  grants: {
    title: "Дошка грантів", subtitle: "Аналітик IT-грантів сортує кожну можливість за відповідністю профілю організації",
    run: "Запустити аналіз", activeAgent: "Активний профіль", newProfile: "+ Новий профіль…", allSettings: "Усі налаштування агента", changeProfile: "Змінити профіль", profileEmpty: "Профіль порожній — агент не знає, для кого шукає гранти.", profileMore: "Показати весь профіль", profileLess: "Згорнути", sourcesCount: "Сайтів-джерел: {{count}}", noAgent: "Немає агента типу «Аналітик грантів». Створіть його у конструкторі.", fits: "Нам підходить", next_year: "На наступний рік", not_for_us: "Не для нас",
    empty: "Поки порожньо", emptyHint: "Запустіть аналіз — агент відкриє сайти з грантами і розкладе їх по колонках.",
    open: "Відкрити", deadline: "Дедлайн", moveTo: "Перемістити", delete: "Прибрати",
    runPrompt: "Проаналізуй актуальні гранти з моїх джерел і порталів (EU Funding & Tenders, Grants.gov, ГУРТ, Громадський простір, House of Europe). Дай вердикт по кожному.",
  },
  analytics: {
    title: "Аналітика", button: "Показати аналітику в графіках", open: "Відкрити", chart: "Графік", table: "Таблиця", source: "Джерело", download: "Завантажити",
    chartsCount_one: "{{count}} графік", chartsCount_few: "{{count}} графіки", chartsCount_many: "{{count}} графіків", chartsCount_other: "{{count}} графіка",
    pdfButton: "Зберегти звіт у PDF",
    prompt: "Покажи аналітику в графіках за результатами цього аналізу: збери числові дані з уже знайденого (за потреби дошукай) і побудуй дашборд через create_dashboard. Лише реальні числа з джерел.",
    pdfPrompt: "Оформи результати цієї розмови як звіт у PDF через create_document: короткий підсумок, основні висновки, таблиці, джерела з посиланнями.",
  },
  common: { loading: "Завантаження…", cancel: "Скасувати", close: "Закрити", error: "Помилка", retry: "Спробувати ще", light: "Світла", dark: "Темна", system: "Системна" },
};

type Dict = typeof uk;

const en: Dict = {
  nav: { chat: "Chat", agents: "Agents", grants: "Grants", accounts: "Accounts", logout: "Log out", myAgents: "My agents", newAgent: "New agent", theme: "Theme" },
  auth: {
    tagline: "Agents that search the internet for you: medicine, grants, any topic.",
    login: "Log in", register: "Create account", email: "Email", password: "Password", name: "Name",
    toRegister: "No account? Sign up", toLogin: "Already registered? Log in", passwordHint: "At least 8 characters",
    invite: "Invite code",
    errors: { invalid_invite: "Wrong invite code", registration_closed: "Registration is closed", too_many_attempts: "Too many attempts. Try again in a few minutes.", invalid_credentials: "Wrong email or password", email_taken: "This email is already registered", invalid_email: "Invalid email", generic: "Something went wrong, please try again" },
  },
  chat: {
    model: "Model", placeholder: "Ask the agent…", send: "Send", stop: "Stop",
    newChat: "New chat", history: "Chats", working: "Agent at work", didSteps: "What the agent did", steps_one: "{{count}} step", steps_few: "{{count}} steps", steps_many: "{{count}} steps", steps_other: "{{count}} steps",
    emptyTitle: "Where shall we start?", emptyHint: "The agent searches the web, reads sources and answers with links.",
    needsAccount: "Connect a model provider account to start using the agent.", connect: "Connect an account",
    cancelled: "Stopped", failed: "Error", thinking: "Thinking…", loadingModels: "Loading models…",
    noModels: "No models", deleteChat: "Delete chat", grantsSaved: "Saved to the grants board: {{count}}", openBoard: "Open board",
    blocked: "Action blocked: the agent has no access to files or a terminal",
    suggestions: {
      "medical-ai": ["Latest studies on LLMs in radiology from the past 6 months", "Which AI products for clinical documentation lead the market?", "What does the EU AI Act require from medical AI systems?"],
      "topic-researcher": ["Find open datasets for medical image recognition", "Overview of AI agents for scientific search in 2026"],
      "it-grants": ["Find open AI grants for Ukrainian universities", "Check GURT and House of Europe for IT faculty grants"],
    },
  },
  accounts: {
    crumbs: ["Settings", "Providers", "Accounts"], title: "Connect an account",
    subtitle: "Sign in with a subscription — no API key to copy. Tokens stay in your own agent profile.",
    haveKey: "Have an API key?", recommended: "Recommended", connected: "Connected", other: "Other providers", apiKeys: "API keys",
    signIn: "Sign in", disconnect: "Disconnect", connectedBadge: "Connected",
    deviceHint: "Opens a verification page — Finder connects automatically",
    codeHint: { claude: "Sign in on claude.ai — then paste the code the page shows", gemini: "Sign in with Google — then paste the code. Gemini models on your Antigravity plan", other: "Sign in on the provider's site — then paste the code" },
    codeStep1: "1. Open the sign-in page and log in to your account.", codeStep2: "2. Approve access — the page shows a code.",
    codeStep3: "3. Copy the code and paste it below.", openSignIn: "Open sign-in page", codeLabel: "Authorization code", codeSubmit: "Connect",
    codeNote: { claude: "Works with a Claude Pro or Max subscription. Anthropic may require extra usage credits to use a subscription in third-party apps.", gemini: "Sign-in is performed by Google's official Antigravity CLI. The session stays in your own profile on the server; Finder never sees the token.", other: "" },
    recommendedHint: "One subscription, hundreds of models — Hermes' native provider",
    keyHint: "The key goes into your Hermes profile and is stored nowhere else",
    modalTitle: "Sign in to {{name}}", step1: "1. Open the verification page.", step2: "2. Enter the code below and approve access.",
    open: "Open verification page", waiting: "Waiting for approval…", approved: "Done! Account connected.",
    failed: "Sign-in failed", starting: "Starting sign-in…", copy: "Copy", copied: "Copied",
    keyTitle: "Add an API key", provider: "Provider", key: "API key", save: "Save", saving: "Checking…",
  },
  agents: {
    title: "Agent builder", subtitle: "Retune an agent for a new task or copy a preset",
    duplicate: "Duplicate", save: "Save agent", saved: "Saved", name: "Name", description: "Description",
    instructions: "Agent instructions", tools: "Search tools", skills: "Skills", sources: "Source sites",
    sourcesHint: "— one per line", orgProfile: "Organisation profile", orgHint: "— used to judge grants", orgTemplateWarning: "This is a template: replace the text in [square brackets] with your organisation's data — otherwise verdicts will be imprecise.", editProfile: "Organisation profile",
    model: "Default model", modelAuto: "As chosen in chat", language: "Answer language", langUi: "Same as interface",
    kind: "Agent type", kindResearch: "Researcher", kindGrants: "Grant analyst",
    isolatedTitle: "Isolated environment", isolatedBody: "The agent only sees internet tools. Files, terminal and code execution are disabled in its Hermes profile.",
    reset: "Reset to preset", delete: "Delete", confirmDelete: "Delete this agent and its chats?", newAgent: "New agent",
    openChat: "Open chat", list: "Agents",
  },
  grants: {
    title: "Grants board", subtitle: "The IT grants analyst sorts every opportunity by how well it fits the organisation profile",
    run: "Run analysis", activeAgent: "Active profile", newProfile: "+ New profile…", allSettings: "All agent settings", changeProfile: "Edit profile", profileEmpty: "The profile is empty — the agent does not know who it is searching for.", profileMore: "Show full profile", profileLess: "Collapse", sourcesCount: "Source sites: {{count}}", noAgent: "No agent of type “Grant analyst”. Create one in the agent builder.", fits: "Fits us", next_year: "Next year", not_for_us: "Not for us",
    empty: "Nothing here yet", emptyHint: "Run the analysis — the agent opens grant sites and sorts them into columns.",
    open: "Open", deadline: "Deadline", moveTo: "Move", delete: "Remove",
    runPrompt: "Analyse current grants from my sources and portals (EU Funding & Tenders, Grants.gov, GURT, Prostir, House of Europe). Give a verdict for each.",
  },
  analytics: {
    title: "Analytics", button: "Show analytics in charts", open: "Open", chart: "Chart", table: "Table", source: "Source", download: "Download",
    chartsCount_one: "{{count}} chart", chartsCount_few: "{{count}} charts", chartsCount_many: "{{count}} charts", chartsCount_other: "{{count}} charts",
    pdfButton: "Save report as PDF",
    prompt: "Show analytics in charts for the results of this analysis: collect the numeric data from what was already found (search for gaps if needed) and build a dashboard with create_dashboard. Only real numbers from sources.",
    pdfPrompt: "Turn the results of this conversation into a PDF report with create_document: short summary, key findings, tables, sources with links.",
  },
  common: { loading: "Loading…", cancel: "Cancel", close: "Close", error: "Error", retry: "Try again", light: "Light", dark: "Dark", system: "System" },
};

const de: Dict = {
  nav: { chat: "Chat", agents: "Agenten", grants: "Förderungen", accounts: "Konten", logout: "Abmelden", myAgents: "Meine Agenten", newAgent: "Neuer Agent", theme: "Design" },
  auth: {
    tagline: "Agenten, die für Sie im Internet recherchieren: Medizin, Förderungen, jedes Thema.",
    login: "Anmelden", register: "Konto erstellen", email: "E-Mail", password: "Passwort", name: "Name",
    toRegister: "Kein Konto? Registrieren", toLogin: "Schon registriert? Anmelden", passwordHint: "Mindestens 8 Zeichen",
    invite: "Einladungscode",
    errors: { invalid_invite: "Falscher Einladungscode", registration_closed: "Registrierung geschlossen", too_many_attempts: "Zu viele Versuche. Bitte in ein paar Minuten erneut versuchen.", invalid_credentials: "Falsche E-Mail oder falsches Passwort", email_taken: "Diese E-Mail ist bereits registriert", invalid_email: "Ungültige E-Mail", generic: "Etwas ist schiefgelaufen, bitte erneut versuchen" },
  },
  chat: {
    model: "Modell", placeholder: "Fragen Sie den Agenten…", send: "Senden", stop: "Stoppen",
    newChat: "Neuer Chat", history: "Chats", working: "Agent arbeitet", didSteps: "Was der Agent getan hat", steps_one: "{{count}} Schritt", steps_few: "{{count}} Schritte", steps_many: "{{count}} Schritte", steps_other: "{{count}} Schritte",
    emptyTitle: "Womit beginnen wir?", emptyHint: "Der Agent durchsucht das Web, liest Quellen und antwortet mit Links.",
    needsAccount: "Verbinden Sie ein Konto eines Modellanbieters, um den Agenten zu nutzen.", connect: "Konto verbinden",
    cancelled: "Gestoppt", failed: "Fehler", thinking: "Denkt nach…", loadingModels: "Modelle werden geladen…",
    noModels: "Keine Modelle", deleteChat: "Chat löschen", grantsSaved: "Auf dem Förderboard gespeichert: {{count}}", openBoard: "Board öffnen",
    blocked: "Aktion blockiert: Der Agent hat keinen Zugriff auf Dateien oder ein Terminal",
    suggestions: {
      "medical-ai": ["Neueste Studien zu LLMs in der Radiologie der letzten 6 Monate", "Welche KI-Produkte für klinische Dokumentation führen den Markt?", "Was verlangt der EU AI Act von medizinischen KI-Systemen?"],
      "topic-researcher": ["Finde offene Datensätze für medizinische Bilderkennung", "Überblick über KI-Agenten für wissenschaftliche Recherche 2026"],
      "it-grants": ["Finde offene KI-Förderungen für ukrainische Universitäten", "Prüfe GURT und House of Europe auf Förderungen für eine IT-Fakultät"],
    },
  },
  accounts: {
    crumbs: ["Einstellungen", "Anbieter", "Konten"], title: "Konto verbinden",
    subtitle: "Mit einem Abo anmelden — kein API-Schlüssel nötig. Tokens bleiben in Ihrem eigenen Agentenprofil.",
    haveKey: "Haben Sie einen API-Schlüssel?", recommended: "Empfohlen", connected: "Verbunden", other: "Weitere Anbieter", apiKeys: "API-Schlüssel",
    signIn: "Anmelden", disconnect: "Trennen", connectedBadge: "Verbunden",
    deviceHint: "Öffnet eine Bestätigungsseite — Finder verbindet sich automatisch",
    codeHint: { claude: "Anmeldung auf claude.ai — danach den angezeigten Code hier einfügen", gemini: "Anmeldung bei Google — danach den Code einfügen. Gemini-Modelle Ihres Antigravity-Plans", other: "Anmeldung beim Anbieter — danach den Code einfügen" },
    codeStep1: "1. Öffnen Sie die Anmeldeseite und melden Sie sich an.", codeStep2: "2. Zugriff bestätigen — die Seite zeigt einen Code.",
    codeStep3: "3. Kopieren Sie den Code und fügen Sie ihn unten ein.", openSignIn: "Anmeldeseite öffnen", codeLabel: "Autorisierungscode", codeSubmit: "Verbinden",
    codeNote: { claude: "Funktioniert mit einem Claude-Pro- oder Max-Abo. Anthropic kann zusätzliches Guthaben (extra usage) für die Nutzung des Abos in Drittanbieter-Apps verlangen.", gemini: "Die Anmeldung übernimmt Googles offizielle Antigravity-CLI. Die Sitzung bleibt in Ihrem eigenen Profil auf dem Server; Finder sieht das Token nie.", other: "" },
    recommendedHint: "Ein Abo, hunderte Modelle — der native Anbieter von Hermes",
    keyHint: "Der Schlüssel landet in Ihrem Hermes-Profil und wird nirgends sonst gespeichert",
    modalTitle: "Anmeldung bei {{name}}", step1: "1. Öffnen Sie die Bestätigungsseite.", step2: "2. Geben Sie den Code unten ein und bestätigen Sie.",
    open: "Bestätigungsseite öffnen", waiting: "Warten auf Bestätigung…", approved: "Fertig! Konto verbunden.",
    failed: "Anmeldung fehlgeschlagen", starting: "Anmeldung wird gestartet…", copy: "Kopieren", copied: "Kopiert",
    keyTitle: "API-Schlüssel hinzufügen", provider: "Anbieter", key: "API-Schlüssel", save: "Speichern", saving: "Wird geprüft…",
  },
  agents: {
    title: "Agenten-Baukasten", subtitle: "Passen Sie einen Agenten an eine neue Aufgabe an oder kopieren Sie eine Vorlage",
    duplicate: "Duplizieren", save: "Agent speichern", saved: "Gespeichert", name: "Name", description: "Beschreibung",
    instructions: "Anweisungen für den Agenten", tools: "Suchwerkzeuge", skills: "Fähigkeiten", sources: "Quell-Websites",
    sourcesHint: "— eine pro Zeile", orgProfile: "Organisationsprofil", orgHint: "— zur Bewertung von Förderungen", orgTemplateWarning: "Dies ist eine Vorlage: Ersetzen Sie den Text in [eckigen Klammern] durch die Daten Ihrer Organisation — sonst sind die Urteile ungenau.", editProfile: "Organisationsprofil",
    model: "Standardmodell", modelAuto: "Wie im Chat gewählt", language: "Antwortsprache", langUi: "Wie die Oberfläche",
    kind: "Agententyp", kindResearch: "Rechercheur", kindGrants: "Förderanalyst",
    isolatedTitle: "Isolierte Umgebung", isolatedBody: "Der Agent sieht nur Internet-Werkzeuge. Dateien, Terminal und Codeausführung sind im Hermes-Profil deaktiviert.",
    reset: "Auf Vorlage zurücksetzen", delete: "Löschen", confirmDelete: "Diesen Agenten samt Chats löschen?", newAgent: "Neuer Agent",
    openChat: "Chat öffnen", list: "Agenten",
  },
  grants: {
    title: "Förderboard", subtitle: "Der IT-Förderanalyst ordnet jede Ausschreibung nach Passung zum Organisationsprofil",
    run: "Analyse starten", activeAgent: "Aktives Profil", newProfile: "+ Neues Profil…", allSettings: "Alle Agenten-Einstellungen", changeProfile: "Profil ändern", profileEmpty: "Das Profil ist leer — der Agent weiß nicht, für wen er sucht.", profileMore: "Ganzes Profil anzeigen", profileLess: "Einklappen", sourcesCount: "Quell-Websites: {{count}}", noAgent: "Kein Agent vom Typ „Förderanalyst“. Erstellen Sie einen im Baukasten.", fits: "Passt zu uns", next_year: "Nächstes Jahr", not_for_us: "Nicht für uns",
    empty: "Noch leer", emptyHint: "Starten Sie die Analyse — der Agent öffnet Förderseiten und sortiert sie in Spalten.",
    open: "Öffnen", deadline: "Frist", moveTo: "Verschieben", delete: "Entfernen",
    runPrompt: "Analysiere aktuelle Förderungen aus meinen Quellen und Portalen (EU Funding & Tenders, Grants.gov, GURT, Prostir, House of Europe). Gib zu jeder ein Urteil.",
  },
  analytics: {
    title: "Analyse", button: "Analyse in Diagrammen zeigen", open: "Öffnen", chart: "Diagramm", table: "Tabelle", source: "Quelle", download: "Herunterladen",
    chartsCount_one: "{{count}} Diagramm", chartsCount_few: "{{count}} Diagramme", chartsCount_many: "{{count}} Diagramme", chartsCount_other: "{{count}} Diagramme",
    pdfButton: "Bericht als PDF speichern",
    prompt: "Zeige die Ergebnisse dieser Analyse in Diagrammen: Sammle die Zahlen aus dem bereits Gefundenen (bei Lücken nachrecherchieren) und erstelle mit create_dashboard ein Dashboard. Nur echte Zahlen aus Quellen.",
    pdfPrompt: "Fasse die Ergebnisse dieses Gesprächs mit create_document als PDF-Bericht zusammen: kurze Zusammenfassung, wichtigste Erkenntnisse, Tabellen, Quellen mit Links.",
  },
  common: { loading: "Wird geladen…", cancel: "Abbrechen", close: "Schließen", error: "Fehler", retry: "Erneut versuchen", light: "Hell", dark: "Dunkel", system: "System" },
};

const saved = (() => { try { return localStorage.getItem("finder.lang"); } catch { return null; } })();

i18n.use(initReactI18next).init({
  resources: { uk: { translation: uk }, en: { translation: en }, de: { translation: de } },
  lng: saved || "uk",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnObjects: true,
});

i18n.on("languageChanged", (lng) => {
  document.documentElement.lang = lng;
  try { localStorage.setItem("finder.lang", lng); } catch { /* storage unavailable */ }
});
document.documentElement.lang = i18n.language;

export default i18n;
