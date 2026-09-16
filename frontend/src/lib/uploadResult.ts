/** What to tell somebody after a ROM upload, refusals included.
 *
 *  The route answers with two lists - `saved` and `rejected`, the second with a
 *  reason per file - and both screens read the first and threw the second away.
 *  Every refusal therefore rendered as "0 ROM(s) uploaded successfully!", a
 *  sentence that says nothing and reads as success. It fired for the ordinary
 *  cases: a file that is not a ROM, a name that belongs to another account, a
 *  subchannel file too large to be one, anything the virus scanner stops.
 *
 *  One place, used by both screens. Two spellings of a message is how the two
 *  copies of a rule drift apart, and this file has watched that happen more
 *  than once.
 */

export interface UploadRejection {
  filename: string;
  /** Set only when the virus scanner stopped it. */
  threat?: string | null;
  /** Why the route refused. `action` is ClamAV's own verdict when `threat` is
   *  set - quarantined, deleted, reported - so it cannot be matched on there. */
  action?: string | null;
}

export interface UploadAnswer {
  saved?: string[];
  rejected?: UploadRejection[];
}

/** The i18n key for one refusal. A reason nobody has written a sentence for
 *  still gets one, rather than an empty line: the file name and "refused" is
 *  more than the screen said before. */
export function reasonKey(r: UploadRejection): string {
  if (r.threat) return 'library.reject_threat';
  switch (r.action) {
    case 'extension_not_recognised': return 'library.reject_extension';
    case 'already_here':             return 'library.reject_already_here';
    case 'subchannel_too_large':     return 'library.reject_subchannel';
    default:                         return 'library.reject_other';
  }
}

/** The project's own `t`, copied from `@/i18n` rather than approximated: the
 *  second argument is either interpolation values or a fallback string, and a
 *  narrower guess here does not accept the real function. */
type Translate = (
  key: string,
  paramsOrFallback?: Record<string, string | number> | string,
) => string;

/** One line for the screen. Empty string while there is nothing to say. */
export function describeUpload(data: UploadAnswer | null, t: Translate): string {
  if (!data) return '';
  const saved = data.saved?.length ?? 0;
  const rejected = data.rejected ?? [];
  if (!rejected.length) return t('library.uploaded_ok', { count: saved });

  const why = rejected
    .map(r => `${r.filename} - ${t(reasonKey(r))}`)
    .join('; ');
  // Nothing landed at all: saying "0 uploaded" first would repeat the very
  // sentence this replaces.
  if (!saved) return `${t('library.uploaded_none', { count: rejected.length })} ${why}`;
  return `${t('library.uploaded_partial', { saved, rejected: rejected.length })} ${why}`;
}

/** Whether the line above should be read as a problem rather than a result.
 *  The screens colour it green today, which is wrong the moment anything was
 *  refused. */
export function uploadHadRefusals(data: UploadAnswer | null): boolean {
  return !!data?.rejected?.length;
}
