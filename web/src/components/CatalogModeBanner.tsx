import type { Copy } from "../i18n";

/** Shown when /readyz reports the model down (SDD §22).
 *
 *  J7 is the argument for the whole architecture: "the model is down" and "the
 *  product is down" must be different sentences, and the banner is where the
 *  difference is said out loud. */
export function CatalogModeBanner({ copy, onCatalog }: { copy: Copy; onCatalog: () => void }) {
  return (
    <div
      data-testid="catalog-mode-banner"
      role="status"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-unverified/30 bg-unverified/[0.08] px-4 py-2.5 text-sm sm:px-6"
    >
      <strong className="font-semibold text-unverified">{copy.catalogModeTitle}</strong>
      <span className="text-ink/80">{copy.catalogModeBody}</span>
      <button
        type="button"
        onClick={onCatalog}
        className="ml-auto rounded border border-unverified/40 px-2.5 py-1 text-xs font-semibold text-unverified hover:bg-unverified/10"
      >
        {copy.catalog}
      </button>
    </div>
  );
}
