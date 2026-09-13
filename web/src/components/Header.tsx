import { ROLES, type Lang, type Role } from "../api/types";
import { LANG_LABEL, UI_LANGS, type Copy } from "../i18n";

/** RoleSwitcher and LanguageToggle. One click to become another role, so a
 *  reviewer can see scoping work inside a minute (PDD §8.1). */
export function Header({
  role,
  language,
  copy,
  onRole,
  onLanguage,
  onCatalog,
}: {
  role: Role;
  language: Lang;
  copy: Copy;
  onRole: (role: Role) => void;
  onLanguage: (language: Lang) => void;
  onCatalog: () => void;
}) {
  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-rule bg-panel px-4 py-3 sm:px-6">
      <h1 className="text-base font-semibold tracking-tight text-ink">{copy.appName}</h1>

      <div className="ml-auto flex items-center gap-2">
        {/* `sr-only` rather than `hidden`: a label with display:none gives the
            select no accessible name at all, so the control that switches ROLE
            -- the one a reviewer reaches for first -- was unnamed below 640px.
            Caught by axe at 375px and by nothing at 1280px. */}
        <label htmlFor="role-switcher" className="sr-only text-xs text-ink/70 sm:not-sr-only">
          {copy.role}
        </label>
        <select
          id="role-switcher"
          data-testid="role-switcher"
          value={role}
          onChange={(event) => onRole(event.target.value as Role)}
          className="rounded border border-rule bg-panel px-2 py-1.5 text-sm text-ink"
        >
          {ROLES.map((name) => (
            <option key={name} value={name}>
              {copy.roleNames[name] ?? name}
            </option>
          ))}
        </select>
      </div>

      <div
        role="group"
        aria-label={copy.language}
        data-testid="language-toggle"
        className="flex overflow-hidden rounded border border-rule"
      >
        {UI_LANGS.map((code) => (
          <button
            key={code}
            type="button"
            aria-pressed={language === code}
            data-testid={`lang-${code}`}
            onClick={() => onLanguage(code)}
            className={`px-2.5 py-1.5 text-sm ${
              language === code ? "bg-ink text-panel" : "bg-panel text-ink/70 hover:bg-surface"
            }`}
          >
            {LANG_LABEL[code]}
          </button>
        ))}
      </div>

      <button
        type="button"
        data-testid="open-catalog"
        onClick={onCatalog}
        className="rounded border border-rule px-2.5 py-1.5 text-sm text-ink/75 hover:bg-surface"
      >
        {copy.catalog}
      </button>
    </header>
  );
}
